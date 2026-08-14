import json
import subprocess

import pytest
import yaml

from maestro_qa import repo_access
from maestro_qa.agents.automatizacion_api import AGENT_REGISTRY, AutomatizacionApiAgent
from maestro_qa.orchestrator import Intake


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)

VALID_PAYLOAD = {
    "api_client_filename": "clients/users_client.py",
    "api_client_code": (
        "import httpx\n\n\n"
        "class UsersClient:\n"
        "    def __init__(self, api_base_url: str) -> None:\n"
        "        self._client = httpx.Client(base_url=api_base_url)\n\n"
        "    def create_user(self, payload: dict) -> httpx.Response:\n"
        "        return self._client.post('/users', json=payload)\n"
    ),
    "test_filename": "tests/test_users_api.py",
    "test_code": (
        "from clients.users_client import UsersClient\n\n\n"
        "def test_create_user_returns_201(api_base_url):\n"
        "    client = UsersClient(api_base_url)\n"
        "    response = client.create_user({'email': 'qa@example.test'})\n"
        "    assert response.status_code == 201\n"
    ),
    "pending_items": [],
}


class FakeProvider:
    def __init__(self, response: str):
        self._response = response

    def complete(self, system, messages, **kwargs):
        return self._response


def test_registers_itself():
    assert isinstance(AGENT_REGISTRY["automatizacion_api"], AutomatizacionApiAgent)


def test_valid_code_returns_both_files_in_content():
    provider = FakeProvider(json.dumps(VALID_PAYLOAD))
    intake = Intake(source="jira_ticket", text="automatizar el endpoint de creación de usuarios")

    result = AutomatizacionApiAgent().run(intake, provider)

    assert result.agent == "automatizacion_api"
    assert "clients/users_client.py" in result.content
    assert "tests/test_users_api.py" in result.content
    assert "class UsersClient" in result.content


def test_pending_items_are_surfaced_not_hidden():
    payload = {**VALID_PAYLOAD, "pending_items": ["Falta el contrato real de error 409"]}
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="jira_ticket", text="endpoint de usuarios")

    result = AutomatizacionApiAgent().run(intake, provider)

    assert "Falta el contrato real de error 409" in result.content


def test_invalid_python_syntax_raises():
    payload = {**VALID_PAYLOAD, "test_code": "def test_broken(:\n    pass"}
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="jira_ticket", text="endpoint de usuarios")

    with pytest.raises(ValueError, match="tests/test_users_api.py"):
        AutomatizacionApiAgent().run(intake, provider)


def test_response_wrapped_in_markdown_fence_is_still_parsed():
    provider = FakeProvider(f"```json\n{json.dumps(VALID_PAYLOAD)}\n```")
    intake = Intake(source="jira_ticket", text="endpoint de usuarios")

    result = AutomatizacionApiAgent().run(intake, provider)
    assert "UsersClient" in result.content


@pytest.mark.parametrize(
    "missing_field", ["api_client_filename", "api_client_code", "test_filename", "test_code"]
)
def test_missing_required_field_raises_clear_error_not_keyerror(missing_field):
    payload = dict(VALID_PAYLOAD)
    del payload[missing_field]
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="jira_ticket", text="endpoint de usuarios")

    with pytest.raises(ValueError, match=missing_field):
        AutomatizacionApiAgent().run(intake, provider)


def test_non_string_code_raises_clear_error_not_typeerror():
    # bug real (auditoría 2026-08-14): _validate solo chequeaba "truthy", no que el
    # código fuera un string -- una lista de líneas pasaba la validación y ast.parse
    # tiraba TypeError sin capturar en vez de un mensaje claro.
    payload = {**VALID_PAYLOAD, "test_code": ["import pytest", "def test_x(): pass"]}
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="jira_ticket", text="endpoint de usuarios")

    with pytest.raises(ValueError, match="se esperaba código como string"):
        AutomatizacionApiAgent().run(intake, provider)


def test_no_automation_repo_configured_means_no_publish_section(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    provider = FakeProvider(json.dumps(VALID_PAYLOAD))
    intake = Intake(source="jira_ticket", text="endpoint de usuarios")

    result = AutomatizacionApiAgent().run(intake, provider)

    assert "Repo de automatización" not in result.content


def test_publishes_generated_code_to_automation_repo_when_configured(tmp_path, monkeypatch):
    bare = tmp_path / "automation.git"
    _git(["init", "-q", "--bare", "--initial-branch=main", str(bare)], tmp_path)
    seed = tmp_path / "seed"
    _git(["clone", "-q", str(bare), str(seed)], tmp_path)
    _git(["config", "user.email", "test@example.com"], seed)
    _git(["config", "user.name", "Test"], seed)
    (seed / "README.md").write_text("qa-automation\n")
    _git(["add", "-A"], seed)
    _git(["commit", "-q", "-m", "init"], seed)
    _git(["push", "-q", "origin", "main"], seed)

    qa_project = tmp_path / "qa-project.yaml"
    qa_project.write_text(
        yaml.safe_dump({"repositories": {"automation": {"url": str(bare), "branch": "main"}}}), encoding="utf-8"
    )
    monkeypatch.setattr(repo_access, "_CACHE_ROOT", tmp_path / "cache")
    monkeypatch.setenv("MAESTRO_GITHUB_TOKEN", "fake-token")
    monkeypatch.chdir(tmp_path)

    provider = FakeProvider(json.dumps(VALID_PAYLOAD))
    intake = Intake(source="jira_ticket", text="endpoint de usuarios")

    result = AutomatizacionApiAgent().run(intake, provider)

    assert "Repo de automatización" in result.content
    assert "Pusheada: sí" in result.content
