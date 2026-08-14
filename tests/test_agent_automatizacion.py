import json

import pytest

from maestro_qa.agents.automatizacion import AGENT_REGISTRY, AutomatizacionAgent
from maestro_qa.orchestrator import Intake

VALID_PAYLOAD = {
    "page_object_filename": "pages/google_login_page.py",
    "page_object_code": (
        "from pages.base_page import BasePage\n\n\n"
        "class GoogleLoginPage(BasePage):\n"
        "    def click_login_with_google(self) -> None:\n"
        "        self.page.get_by_role('button', name='Iniciar sesión con Google').click()\n"
    ),
    "test_filename": "tests/test_google_login.py",
    "test_code": (
        "from playwright.sync_api import expect\n\n"
        "from pages.google_login_page import GoogleLoginPage\n\n\n"
        "def test_login_with_google(page, base_url):\n"
        "    login_page = GoogleLoginPage(page, base_url)\n"
        "    login_page.open('/login')\n"
        "    login_page.click_login_with_google()\n"
        "    expect(page).to_have_url(f'{base_url}/dashboard')\n"
    ),
    "pending_items": [],
}


class FakeProvider:
    def __init__(self, response: str):
        self._response = response

    def complete(self, system, messages, **kwargs):
        return self._response


def test_registers_itself():
    assert isinstance(AGENT_REGISTRY["automatizacion"], AutomatizacionAgent)


def test_valid_code_returns_both_files_in_content():
    provider = FakeProvider(json.dumps(VALID_PAYLOAD))
    intake = Intake(source="spec", text="login con Google")

    result = AutomatizacionAgent().run(intake, provider)

    assert result.agent == "automatizacion"
    assert "pages/google_login_page.py" in result.content
    assert "tests/test_google_login.py" in result.content
    assert "class GoogleLoginPage(BasePage)" in result.content


def test_pending_items_are_surfaced_not_hidden():
    payload = {**VALID_PAYLOAD, "pending_items": ["Falta el selector real del botón de logout"]}
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="jira_ticket", text="logout")

    result = AutomatizacionAgent().run(intake, provider)

    assert "Falta el selector real del botón de logout" in result.content


def test_invalid_python_syntax_raises():
    payload = {**VALID_PAYLOAD, "test_code": "def test_broken(:\n    pass"}
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="spec", text="login con Google")

    with pytest.raises(ValueError, match="tests/test_google_login.py"):
        AutomatizacionAgent().run(intake, provider)


def test_response_wrapped_in_markdown_fence_is_still_parsed():
    provider = FakeProvider(f"```json\n{json.dumps(VALID_PAYLOAD)}\n```")
    intake = Intake(source="spec", text="login con Google")

    result = AutomatizacionAgent().run(intake, provider)
    assert "GoogleLoginPage" in result.content


@pytest.mark.parametrize(
    "missing_field", ["page_object_filename", "page_object_code", "test_filename", "test_code"]
)
def test_missing_required_field_raises_clear_error_not_keyerror(missing_field):
    payload = dict(VALID_PAYLOAD)
    del payload[missing_field]
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="spec", text="login con Google")

    with pytest.raises(ValueError, match=missing_field):
        AutomatizacionAgent().run(intake, provider)


def test_response_with_trailing_prose_and_stray_brace_is_still_parsed():
    # bug real de extracción de JSON (spec 022): un regex greedy se confundía con
    # cualquier otra llave en el texto circundante.
    raw = f"{json.dumps(VALID_PAYLOAD)}\n\nNota: el campo `{{base_url}}` ya está resuelto."
    provider = FakeProvider(raw)
    intake = Intake(source="spec", text="login con Google")

    result = AutomatizacionAgent().run(intake, provider)
    assert "GoogleLoginPage" in result.content
