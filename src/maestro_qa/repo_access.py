import hashlib
import os
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import yaml

from . import onboarding
from .providers.base import Tool, ToolExecutor

_CACHE_ROOT = Path.home() / ".cache" / "maestro-qa" / "repos"

TOOLS: list[Tool] = [
    {
        "name": "list_files",
        "description": "Lista archivos y carpetas bajo un path del repo (no recursivo).",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Path relativo al root del repo, default '.'"}},
            "required": [],
        },
    },
    {
        "name": "read_file",
        "description": "Lee el contenido completo de un archivo del repo.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Path relativo al root del repo"}},
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": (
            "Escribe/sobreescribe un archivo del repo. Usalo para agregar un atributo "
            "data-testid faltante a un componente existente, nunca para el Page Object ni "
            "el test (esos van en la respuesta JSON final)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path relativo al root del repo"},
                "content": {"type": "string", "description": "Contenido completo nuevo del archivo"},
            },
            "required": ["path", "content"],
        },
    },
]

# Para agentes de solo lectura (ej. calidad_codigo, spec 025): nunca se les ofrece
# write_file en el schema.
READ_ONLY_TOOLS: list[Tool] = [tool for tool in TOOLS if tool["name"] != "write_file"]


def _slug(url: str) -> str:
    digest = hashlib.sha256(url.encode()).hexdigest()[:12]
    name = url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
    return f"{name}-{digest}"


def _resolve_safe(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    if candidate != root.resolve() and root.resolve() not in candidate.parents:
        raise ValueError(f"path fuera del repo: {relative!r}")
    # El LLM no controla el estado interno de git — sin esto, write_file(".git/hooks/
    # pre-commit", ...) o ".git/config" escriben directo al repo git real (bug real,
    # encontrado en auditoría 2026-08-14).
    if candidate == root.resolve() / ".git" or (root.resolve() / ".git") in candidate.parents:
        raise ValueError(f"path dentro de .git/, no permitido: {relative!r}")
    return candidate


@dataclass
class RepoAccess:
    path: Path
    touched_files: set[str] = field(default_factory=set)

    def list_files(self, path: str = ".") -> str:
        target = _resolve_safe(self.path, path)
        if not target.is_dir():
            return f"error: {path!r} no es un directorio"
        entries = sorted(p.name + ("/" if p.is_dir() else "") for p in target.iterdir() if p.name != ".git")
        return "\n".join(entries) if entries else "(vacío)"

    def read_file(self, path: str) -> str:
        target = _resolve_safe(self.path, path)
        if not target.is_file():
            return f"error: {path!r} no es un archivo"
        return target.read_text(encoding="utf-8", errors="replace")

    def write_file(self, path: str, content: str) -> str:
        target = _resolve_safe(self.path, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        self.touched_files.add(path)
        return "ok"

    def execute(self, name: str, args: dict[str, object]) -> str:
        try:
            if name == "list_files":
                return self.list_files(str(args.get("path", ".")))
            if name == "read_file":
                return self.read_file(str(args["path"]))
            if name == "write_file":
                return self.write_file(str(args["path"]), str(args["content"]))
            return f"error: herramienta desconocida {name!r}"
        except (ValueError, OSError, KeyError, TypeError, AttributeError) as exc:
            # El LLM puede mandar args con la forma equivocada (path como lista, content
            # ausente, etc.) — nunca debe tirar una excepción no manejada que rompa todo
            # el loop de tool-calling del provider.
            return f"error: {exc}"

    def read_only_executor(self) -> ToolExecutor:
        """Envuelve execute() rechazando write_file como defensa en profundidad — un LLM
        puede alucinar una tool call a algo que no se le ofreció en el schema (ver
        READ_ONLY_TOOLS, usado por agentes de solo lectura como calidad_codigo, spec 025)."""

        def executor(name: str, args: dict[str, object]) -> str:
            if name == "write_file":
                return "error: acceso de solo lectura, write_file no está permitido acá"
            return self.execute(name, args)

        return executor

    def commit_changes(self, feature_slug: str) -> tuple[str, str] | None:
        """Crea una rama nueva y comitea los archivos tocados. No pushea. Devuelve
        (branch, commit_sha) o None si no se tocó ningún archivo."""
        if not self.touched_files:
            return None

        timestamp = datetime.now(tz=UTC).strftime("%Y%m%d%H%M%S%f")
        branch = f"automatizacion/{feature_slug}-{timestamp}"
        _run(["git", "checkout", "-b", branch], cwd=self.path)
        _run(["git", "add", "-A"], cwd=self.path)
        # No depende de que la máquina tenga identidad git configurada (ambiente fresco,
        # CI, container) — el commit automatizado siempre firma como Maestro QA.
        _run(
            ["git", "commit", "-m", f"automatizacion: agrega selectores de test para {feature_slug}"],
            cwd=self.path,
            env={
                "GIT_AUTHOR_NAME": "Maestro QA",
                "GIT_AUTHOR_EMAIL": "maestro-qa@localhost",
                "GIT_COMMITTER_NAME": "Maestro QA",
                "GIT_COMMITTER_EMAIL": "maestro-qa@localhost",
            },
        )
        commit_sha = _run(["git", "rev-parse", "HEAD"], cwd=self.path).stdout.strip()
        return branch, commit_sha


def _run(args: list[str], cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    full_env = {**os.environ, **env} if env else None
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False, env=full_env)
    if result.returncode != 0:
        raise RuntimeError(f"{' '.join(args)} falló: {result.stderr.strip()}")
    return result


def _clone_or_refresh(url: str, branch: str, cache_dir: Path) -> None:
    if (cache_dir / ".git").exists():
        target_branch = branch or "HEAD"
        _run(["git", "fetch", "origin", target_branch], cwd=cache_dir)
        # Se hace checkout --detach a FETCH_HEAD ANTES del reset: una corrida anterior
        # puede haber dejado un branch de automatizacion/* checked out (spec 023) — si se
        # resetea directo sobre ese branch en vez de detachear primero, el reset --hard
        # mueve SU ref a FETCH_HEAD y el commit de esa corrida anterior se pierde (bug
        # real, encontrado probando contra un repo real: CDA-88).
        _run(["git", "checkout", "--detach", "FETCH_HEAD"], cwd=cache_dir)
        _run(["git", "reset", "--hard", "FETCH_HEAD"], cwd=cache_dir)
        return

    cache_dir.parent.mkdir(parents=True, exist_ok=True)
    args = ["git", "clone", "--depth", "1"]
    if branch:
        args += ["--branch", branch]
    args += [url, str(cache_dir)]
    _run(args, cwd=cache_dir.parent)


class RepoAccessError(Exception):
    """Repo configurado pero algo falló (verificación, clone). Distinto de "no hay repo
    configurado" (eso devuelve None sin error — es el caso común, no una falla)."""


def get_repo(qa_project_path: Path, repo_key: str = "frontend") -> RepoAccess | None:
    """None si no hay repo `repo_key` configurado — comportamiento idéntico al de
    siempre, sin repo. Levanta RepoAccessError si HAY uno configurado pero algo falló
    (verificación, clone) — quien llama lo reporta en pending_items."""
    if not qa_project_path.exists():
        return None

    try:
        document = yaml.safe_load(qa_project_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise RepoAccessError(f"qa-project.yaml inválido: {exc}") from exc

    repo_config = (document.get("repositories") or {}).get(repo_key) or {}
    url = repo_config.get("url")
    if not url:
        return None

    branch = repo_config.get("branch", "")
    try:
        status = onboarding._verify_repo(url, branch)
    except OSError as exc:
        raise RepoAccessError(f"no se pudo verificar el repo: {exc}") from exc
    if status.get("status") != "VERIFIED":
        raise RepoAccessError(f"repo no verificado: {status.get('message', status.get('status'))}")

    cache_dir = _CACHE_ROOT / _slug(url)
    try:
        _clone_or_refresh(url, branch, cache_dir)
    except RuntimeError as exc:
        raise RepoAccessError(f"no se pudo clonar/actualizar el repo: {exc}") from exc

    return RepoAccess(path=cache_dir)


def get_frontend_repo(qa_project_path: Path) -> RepoAccess | None:
    return get_repo(qa_project_path, "frontend")
