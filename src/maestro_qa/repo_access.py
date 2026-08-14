import hashlib
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import yaml

from . import onboarding
from .providers.base import Tool

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


def _slug(url: str) -> str:
    digest = hashlib.sha256(url.encode()).hexdigest()[:12]
    name = url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
    return f"{name}-{digest}"


def _resolve_safe(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    if candidate != root.resolve() and root.resolve() not in candidate.parents:
        raise ValueError(f"path fuera del repo: {relative!r}")
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
        except (ValueError, OSError, KeyError) as exc:
            return f"error: {exc}"

    def commit_changes(self, feature_slug: str) -> tuple[str, str] | None:
        """Crea una rama nueva y comitea los archivos tocados. No pushea. Devuelve
        (branch, commit_sha) o None si no se tocó ningún archivo."""
        if not self.touched_files:
            return None

        timestamp = datetime.now(tz=UTC).strftime("%Y%m%d%H%M%S")
        branch = f"automatizacion/{feature_slug}-{timestamp}"
        _run(["git", "checkout", "-b", branch], cwd=self.path)
        _run(["git", "add", "-A"], cwd=self.path)
        _run(
            ["git", "commit", "-m", f"automatizacion: agrega selectores de test para {feature_slug}"],
            cwd=self.path,
        )
        commit_sha = _run(["git", "rev-parse", "HEAD"], cwd=self.path).stdout.strip()
        return branch, commit_sha


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"{' '.join(args)} falló: {result.stderr.strip()}")
    return result


def _clone_or_refresh(url: str, branch: str, cache_dir: Path) -> None:
    if (cache_dir / ".git").exists():
        target_branch = branch or "HEAD"
        _run(["git", "fetch", "origin", target_branch], cwd=cache_dir)
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


def get_frontend_repo(qa_project_path: Path) -> RepoAccess | None:
    """None si no hay repo de frontend configurado — comportamiento idéntico al de
    siempre, sin repo. Levanta RepoAccessError si HAY uno configurado pero algo falló
    (verificación, clone) — automatizacion.py lo reporta en pending_items."""
    if not qa_project_path.exists():
        return None

    try:
        document = yaml.safe_load(qa_project_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise RepoAccessError(f"qa-project.yaml inválido: {exc}") from exc

    frontend = (document.get("repositories") or {}).get("frontend") or {}
    url = frontend.get("url")
    if not url:
        return None

    branch = frontend.get("branch", "")
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
