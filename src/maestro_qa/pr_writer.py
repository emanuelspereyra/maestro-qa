import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import yaml

from . import repo_access
from .repo_access import RepoAccess


class PrWriterError(Exception):
    pass


@dataclass
class PublishResult:
    branch: str | None = None
    commit_sha: str | None = None
    pushed: bool = False
    pr_url: str | None = None
    error: str | None = None


def _parse_github_repo(url: str) -> tuple[str, str] | None:
    """(owner, repo) si `url` es un repo de github.com, sino None — CDA-60 solo abre PR
    en GitHub, otros providers quedan como push manual (ver spec 026)."""
    if "github.com" not in url.lower():
        return None
    path = url.split(":", 1)[-1] if url.startswith("git@") else urlsplit(url).path
    parts = [part for part in path.strip("/").removesuffix(".git").split("/") if part]
    if len(parts) < 2:
        return None
    return parts[0], parts[1]


def push_branch(repo: RepoAccess, branch: str, token: str) -> None:
    """git push con el token vía header de esa invocación puntual — nunca se guarda en
    la URL ni en .git/config."""
    repo_access._run(
        ["git", "-c", f"http.extraHeader=Authorization: Bearer {token}", "push", "origin", branch],
        cwd=repo.path,
        env={"GIT_TERMINAL_PROMPT": "0"},
    )


def open_pull_request(repo_url: str, token: str, branch: str, base: str, title: str, body: str) -> str:
    parsed = _parse_github_repo(repo_url)
    if parsed is None:
        raise PrWriterError(f"no es un repo de GitHub, no se puede abrir PR automático: {repo_url}")
    owner, repo_name = parsed

    response = httpx.post(
        f"https://api.github.com/repos/{owner}/{repo_name}/pulls",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"title": title, "body": body, "head": branch, "base": base or "main"},
        timeout=30,
    )
    if response.status_code >= 400:
        raise PrWriterError(f"GitHub API respondió {response.status_code}: {response.text[:300]}")
    pr_url = response.json().get("html_url")
    if not pr_url:
        raise PrWriterError(f"GitHub API no devolvió html_url: {response.text[:300]}")
    return str(pr_url)


def publish_generated_code(
    qa_project_path: Path,
    feature_slug: str,
    files: dict[str, str],
    pr_title: str,
    pr_body: str,
) -> PublishResult | None:
    """None si repositories.automation no está configurado (comportamiento actual, sin
    cambios). Si está configurado, nunca levanta — cualquier falla queda en
    PublishResult.error y el código ya generado se sigue devolviendo igual (spec 026)."""
    try:
        repo = repo_access.get_repo(qa_project_path, "automation")
    except repo_access.RepoAccessError as exc:
        return PublishResult(error=f"no se pudo usar el repo de automatización ({exc})")
    if repo is None:
        return None

    for filename, code in files.items():
        repo.write_file(filename, code)

    try:
        commit = repo.commit_changes(feature_slug)
    except RuntimeError as exc:
        return PublishResult(error=f"no se pudo comitear en el repo de automatización ({exc})")
    if commit is None:
        return PublishResult(error="no había cambios para comitear en el repo de automatización")

    branch, commit_sha = commit
    result = PublishResult(branch=branch, commit_sha=commit_sha)

    token = os.environ.get("MAESTRO_GITHUB_TOKEN")
    if not token:
        result.error = "falta MAESTRO_GITHUB_TOKEN, quedó comiteado localmente sin pushear"
        return result

    document = yaml.safe_load(qa_project_path.read_text(encoding="utf-8")) or {}
    repo_config = (document.get("repositories") or {}).get("automation") or {}
    repo_url = str(repo_config["url"])
    base_branch = str(repo_config.get("branch") or "main")

    try:
        push_branch(repo, branch, token)
    except RuntimeError as exc:
        result.error = f"no se pudo pushear la rama ({exc})"
        return result
    result.pushed = True

    try:
        result.pr_url = open_pull_request(repo_url, token, branch, base_branch, pr_title, pr_body)
    except PrWriterError as exc:
        result.error = f"se pusheó la rama pero no se pudo abrir el PR ({exc}) — abrilo a mano"

    return result
