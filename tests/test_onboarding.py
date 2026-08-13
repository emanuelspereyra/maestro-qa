import os

import yaml

from maestro_qa import onboarding


def test_ensure_project_creates_qa_project_yaml_when_missing(tmp_path):
    status = onboarding.ensure_project(tmp_path)

    assert status.qa_project_path == tmp_path / "qa-project.yaml"
    assert status.qa_project_path.exists()
    assert status.repos == {}


def test_ensure_project_does_not_recreate_existing_file(tmp_path):
    qa_project = tmp_path / "qa-project.yaml"
    qa_project.write_text("marker: no-tocar\n")

    onboarding.ensure_project(tmp_path)

    assert "marker: no-tocar" in qa_project.read_text()


def test_ensure_project_skips_verification_when_no_repo_configured(tmp_path, monkeypatch):
    def fail_if_called(url, branch):
        raise AssertionError("no debería verificar nada sin URL configurada")

    monkeypatch.setattr(onboarding, "_verify_repo", fail_if_called)

    status = onboarding.ensure_project(tmp_path)

    assert status.repos == {}


def test_ensure_project_verifies_configured_repo_without_hitting_network(tmp_path, monkeypatch):
    qa_project = tmp_path / "qa-project.yaml"
    onboarding._create_project_file(qa_project)
    document = yaml.safe_load(qa_project.read_text(encoding="utf-8"))
    document["repositories"]["frontend"]["url"] = "https://github.com/example/repo.git"
    document["repositories"]["frontend"]["branch"] = "main"
    qa_project.write_text(yaml.safe_dump(document), encoding="utf-8")

    calls = []

    def fake_verify(url, branch):
        calls.append((url, branch))
        return {"status": "VERIFIED"}

    monkeypatch.setattr(onboarding, "_verify_repo", fake_verify)

    status = onboarding.ensure_project(tmp_path)

    assert calls == [("https://github.com/example/repo.git", "main")]
    assert status.repos["frontend"] == {"status": "VERIFIED"}


def test_ensure_project_reports_env_status_without_exposing_values(tmp_path):
    os.environ["MAESTRO_API_KEY"] = "sk-super-secret"
    try:
        status = onboarding.ensure_project(tmp_path)
        assert status.env["MAESTRO_API_KEY"] is True
        assert "sk-super-secret" not in str(status.env)
    finally:
        os.environ.pop("MAESTRO_API_KEY", None)
