import subprocess

import httpx
import pytest
import yaml

from maestro_qa import pr_writer, repo_access


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def bare_automation_repo(tmp_path):
    """Repo bare real como "remoto" -- push real de verdad, sin mockear git."""
    bare = tmp_path / "automation.git"
    _git(["init", "-q", "--bare", "--initial-branch=main", str(bare)], tmp_path)

    # necesita un commit inicial en main para que get_repo pueda clonar/verificar la rama
    seed = tmp_path / "seed"
    _git(["clone", "-q", str(bare), str(seed)], tmp_path)
    _git(["config", "user.email", "test@example.com"], seed)
    _git(["config", "user.name", "Test"], seed)
    (seed / "README.md").write_text("qa-automation\n")
    _git(["add", "-A"], seed)
    _git(["commit", "-q", "-m", "init"], seed)
    _git(["push", "-q", "origin", "main"], seed)
    return bare


@pytest.fixture
def qa_project_with_automation_repo(tmp_path, bare_automation_repo, monkeypatch):
    qa_project = tmp_path / "qa-project.yaml"
    qa_project.write_text(
        yaml.safe_dump({"repositories": {"automation": {"url": str(bare_automation_repo), "branch": "main"}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(repo_access, "_CACHE_ROOT", tmp_path / "cache")
    return qa_project


def test_returns_none_without_automation_repo_configured(tmp_path):
    qa_project = tmp_path / "qa-project.yaml"
    qa_project.write_text(yaml.safe_dump({"repositories": {}}), encoding="utf-8")

    result = pr_writer.publish_generated_code(
        qa_project, "login", {"pages/login_page.py": "x = 1\n"}, "title", "body"
    )

    assert result is None


def test_without_github_token_commits_locally_and_reports_missing_token(
    qa_project_with_automation_repo, monkeypatch
):
    monkeypatch.delenv("MAESTRO_GITHUB_TOKEN", raising=False)

    result = pr_writer.publish_generated_code(
        qa_project_with_automation_repo, "login", {"pages/login_page.py": "x = 1\n"}, "title", "body"
    )

    assert result.branch is not None
    assert result.pushed is False
    assert result.pr_url is None
    assert "MAESTRO_GITHUB_TOKEN" in result.error


def test_pushes_for_real_to_a_bare_repo_when_provider_is_not_github(
    qa_project_with_automation_repo, bare_automation_repo, monkeypatch
):
    monkeypatch.setenv("MAESTRO_GITHUB_TOKEN", "fake-token")

    result = pr_writer.publish_generated_code(
        qa_project_with_automation_repo,
        "login",
        {"pages/login_page.py": "class LoginPage:\n    pass\n"},
        "test(automatizacion): login",
        "body",
    )

    assert result.pushed is True
    assert result.pr_url is None
    assert "abrilo a mano" in result.error

    log = subprocess.run(
        ["git", "log", result.branch, "--oneline"], cwd=bare_automation_repo, capture_output=True, text=True, check=True
    )
    assert result.commit_sha[:7] in log.stdout

    show = subprocess.run(
        ["git", "show", f"{result.branch}:pages/login_page.py"],
        cwd=bare_automation_repo,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "class LoginPage" in show.stdout


def test_commit_failure_is_reported_without_crashing(qa_project_with_automation_repo, monkeypatch):
    monkeypatch.setenv("MAESTRO_GITHUB_TOKEN", "fake-token")
    monkeypatch.setattr(
        repo_access.RepoAccess,
        "commit_changes",
        lambda self, feature_slug: (_ for _ in ()).throw(RuntimeError("git commit falló feo")),
    )

    result = pr_writer.publish_generated_code(
        qa_project_with_automation_repo, "login", {"pages/login_page.py": "x = 1\n"}, "title", "body"
    )

    assert result.error is not None
    assert "no se pudo comitear" in result.error


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://github.com/emanuelspereyra/qa-automation.git", ("emanuelspereyra", "qa-automation")),
        ("https://github.com/emanuelspereyra/qa-automation", ("emanuelspereyra", "qa-automation")),
        ("git@github.com:emanuelspereyra/qa-automation.git", ("emanuelspereyra", "qa-automation")),
        ("https://gitlab.com/emanuelspereyra/qa-automation.git", None),
    ],
)
def test_parse_github_repo(url, expected):
    assert pr_writer._parse_github_repo(url) == expected


def test_open_pull_request_returns_html_url_on_success(monkeypatch):
    def fake_post(url, headers, json, timeout):
        assert json["head"] == "automatizacion/login-123"
        assert json["base"] == "main"
        return httpx.Response(201, json={"html_url": "https://github.com/x/y/pull/1"})

    monkeypatch.setattr(httpx, "post", fake_post)

    pr_url = pr_writer.open_pull_request(
        "https://github.com/x/y.git", "token", "automatizacion/login-123", "main", "title", "body"
    )

    assert pr_url == "https://github.com/x/y/pull/1"


def test_open_pull_request_raises_clear_error_on_api_failure(monkeypatch):
    monkeypatch.setattr(
        httpx, "post", lambda url, headers, json, timeout: httpx.Response(401, json={"message": "Bad credentials"})
    )

    with pytest.raises(pr_writer.PrWriterError, match="401"):
        pr_writer.open_pull_request("https://github.com/x/y.git", "bad-token", "branch", "main", "t", "b")


def test_open_pull_request_raises_for_non_github_repo():
    with pytest.raises(pr_writer.PrWriterError, match="GitHub"):
        pr_writer.open_pull_request("https://gitlab.com/x/y.git", "token", "branch", "main", "t", "b")
