import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import config, vendor_bundle

PROJECT_CONFIG_PATH = Path("qa-project.yaml")


@dataclass
class ProjectStatus:
    qa_project_path: Path
    repos: dict[str, dict[str, object]] = field(default_factory=dict)
    env: dict[str, bool] = field(default_factory=dict)


def _create_project_file(path: Path) -> None:
    script = vendor_bundle.scripts_dir() / "init_qa_project.py"
    result = subprocess.run(
        [
            "python3",
            str(script),
            "--output",
            str(path),
            "--project-name",
            "maestro-qa",
            "--non-interactive",
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=path.parent if path.parent != Path() else None,
    )
    if result.returncode != 0:
        raise RuntimeError(f"init_qa_project.py falló: {result.stdout}{result.stderr}")


def _verify_repo(url: str, branch: str) -> dict[str, object]:
    script = vendor_bundle.scripts_dir() / "verify_repository.py"
    args = ["python3", str(script), "--url", url]
    if branch:
        args += ["--branch", branch]
    result = subprocess.run(args, capture_output=True, text=True, check=False)
    try:
        return dict(json.loads(result.stdout))
    except ValueError:
        return {"status": "UNKNOWN", "message": result.stdout.strip()}


def ensure_project(project_dir: Path | None = None) -> ProjectStatus:
    directory = project_dir or Path.cwd()
    qa_project_path = directory / PROJECT_CONFIG_PATH

    if not qa_project_path.exists():
        _create_project_file(qa_project_path)

    document = yaml.safe_load(qa_project_path.read_text(encoding="utf-8")) or {}
    repositories = document.get("repositories", {}) or {}

    repos_status: dict[str, dict[str, object]] = {}
    for repo_name in ("frontend", "backend", "automation"):
        repo = repositories.get(repo_name) or {}
        url = repo.get("url")
        if url:
            repos_status[repo_name] = _verify_repo(url, repo.get("branch", ""))

    config.load_env_file()
    return ProjectStatus(
        qa_project_path=qa_project_path,
        repos=repos_status,
        env=config.env_status(),
    )
