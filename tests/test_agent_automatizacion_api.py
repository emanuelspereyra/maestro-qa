import json

import pytest

from maestro_qa.agents.automatizacion_api import AGENT_REGISTRY, AutomatizacionApiAgent
from maestro_qa.orchestrator import Intake

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
