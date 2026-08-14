import subprocess
from pathlib import Path

import pytest
import yaml

from maestro_qa import repo_access


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def remote_repo(tmp_path):
    remote = tmp_path / "remote"
    remote.mkdir()
    _git(["init", "-q", "--initial-branch=main"], remote)
    _git(["config", "user.email", "test@example.com"], remote)
    _git(["config", "user.name", "Test"], remote)
    (remote / "src").mkdir()
    (remote / "src" / "login.jsx").write_text("export const Login = () => <button>Login</button>\n")
    _git(["add", "-A"], remote)
    _git(["commit", "-q", "-m", "init"], remote)
    return remote


@pytest.fixture
def qa_project_with_repo(tmp_path, remote_repo):
    qa_project = tmp_path / "qa-project.yaml"
    qa_project.write_text(
        yaml.safe_dump({"repositories": {"frontend": {"url": str(remote_repo), "branch": "main"}}}),
        encoding="utf-8",
    )
    return qa_project


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(repo_access, "_CACHE_ROOT", tmp_path / "cache")


def test_returns_none_without_qa_project_file(tmp_path):
    assert repo_access.get_frontend_repo(tmp_path / "qa-project.yaml") is None


def test_returns_none_without_frontend_url(tmp_path):
    qa_project = tmp_path / "qa-project.yaml"
    qa_project.write_text(yaml.safe_dump({"repositories": {}}), encoding="utf-8")
    assert repo_access.get_frontend_repo(qa_project) is None


def test_clones_real_local_repo_and_exposes_its_files(qa_project_with_repo):
    repo = repo_access.get_frontend_repo(qa_project_with_repo)

    assert repo is not None
    assert "src/" in repo.list_files(".")
    assert "Login" in repo.read_file("src/login.jsx")


def test_raises_repo_access_error_for_unreachable_repo(tmp_path):
    qa_project = tmp_path / "qa-project.yaml"
    qa_project.write_text(
        yaml.safe_dump({"repositories": {"frontend": {"url": str(tmp_path / "does-not-exist"), "branch": "main"}}}),
        encoding="utf-8",
    )
    with pytest.raises(repo_access.RepoAccessError):
        repo_access.get_frontend_repo(qa_project)


def test_write_file_then_commit_creates_new_branch(qa_project_with_repo):
    # sin git config user.email/name en el clone (bug real, CDA-88: CI no tiene
    # identidad git ambiente y esto rompía con "Author identity unknown") —
    # commit_changes tiene que funcionar solo, sin depender de config externa.
    repo = repo_access.get_frontend_repo(qa_project_with_repo)
    repo.write_file("src/login.jsx", "export const Login = () => <button data-testid='id-testautomation-login'>Login</button>\n")
    commit = repo.commit_changes("login")

    assert commit is not None
    branch, _sha = commit
    assert branch.startswith("automatizacion/login-")
    current_branch = subprocess.run(
        ["git", "branch", "--show-current"], cwd=repo.path, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert current_branch == branch
    assert "id-testautomation-login" in (repo.path / "src" / "login.jsx").read_text()


def test_commit_changes_returns_none_when_nothing_was_written(qa_project_with_repo):
    repo = repo_access.get_frontend_repo(qa_project_with_repo)
    assert repo.commit_changes("login") is None


def test_read_file_rejects_path_escaping_repo_root(qa_project_with_repo):
    repo = repo_access.get_frontend_repo(qa_project_with_repo)
    with pytest.raises(ValueError, match="fuera del repo"):
        repo.read_file("../../etc/passwd")


def test_execute_returns_error_string_instead_of_raising(qa_project_with_repo):
    repo = repo_access.get_frontend_repo(qa_project_with_repo)
    result = repo.execute("read_file", {"path": "../../etc/passwd"})
    assert result.startswith("error:")


def test_refreshing_cache_does_not_destroy_a_previous_automatizacion_branch(qa_project_with_repo, remote_repo):
    # bug real (CDA-88, encontrado probando contra un repo real): si una corrida anterior
    # dejó un branch automatizacion/* checked out con su propio commit, un refresh que
    # resetea directo sobre ese branch (en vez de detachear primero) mueve su ref a
    # FETCH_HEAD y el commit se pierde.
    first = repo_access.get_frontend_repo(qa_project_with_repo)
    first.write_file("src/login.jsx", "modificado por la corrida 1\n")
    branch, commit_sha = first.commit_changes("login")

    second = repo_access.get_frontend_repo(qa_project_with_repo)

    assert second.path == first.path
    preserved_commit = subprocess.run(
        ["git", "cat-file", "-e", commit_sha], cwd=second.path, capture_output=True, check=False
    )
    assert preserved_commit.returncode == 0, "el commit de la corrida anterior no debería perderse"
    branch_tip = subprocess.run(
        ["git", "rev-parse", branch], cwd=second.path, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert branch_tip == commit_sha, "el branch de la corrida anterior no debería moverse"


def test_reusing_cache_does_a_fetch_reset_instead_of_recloning(qa_project_with_repo, remote_repo):
    first = repo_access.get_frontend_repo(qa_project_with_repo)
    (remote_repo / "src" / "new_file.jsx").write_text("export const New = () => null\n")
    _git(["add", "-A"], remote_repo)
    _git(["commit", "-q", "-m", "second commit"], remote_repo)

    second = repo_access.get_frontend_repo(qa_project_with_repo)

    assert first.path == second.path
    assert "new_file.jsx" in second.list_files("src")
