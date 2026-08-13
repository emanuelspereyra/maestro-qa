import json

import pytest

from maestro_qa.agents.documentacion import AGENT_REGISTRY, DocumentacionAgent
from maestro_qa.orchestrator import Intake

VALID_PAYLOAD = {
    "doc_type": "user_guide",
    "title": "Iniciar sesión con Google",
    "summary": "Los usuarios pueden loguearse usando su cuenta de Google en vez de email y contraseña.",
    "sections": [
        {"heading": "Cómo usarlo", "content": "Hacer click en 'Iniciar sesión con Google' en la pantalla de login."},
        {"heading": "Casos borde", "content": "Si el usuario cancela el consentimiento, vuelve al login sin sesión."},
    ],
    "pending_items": [],
}


class FakeProvider:
    def __init__(self, response: str):
        self._response = response

    def complete(self, system, messages, **kwargs):
        return self._response


def test_registers_itself():
    assert isinstance(AGENT_REGISTRY["documentacion"], DocumentacionAgent)


def test_valid_doc_renders_title_summary_and_sections():
    provider = FakeProvider(json.dumps(VALID_PAYLOAD))
    intake = Intake(source="jira_ticket", text="documentar el login con Google")

    result = DocumentacionAgent().run(intake, provider)

    assert result.agent == "documentacion"
    assert "[user_guide]" in result.content
    assert "Iniciar sesión con Google" in result.content
    assert "Cómo usarlo" in result.content
    assert "Casos borde" in result.content


def test_pending_items_are_surfaced_not_hidden():
    payload = {**VALID_PAYLOAD, "pending_items": ["Falta el nombre final de la feature para el changelog"]}
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="spec", text="documentar el login")

    result = DocumentacionAgent().run(intake, provider)

    assert "Falta el nombre final de la feature para el changelog" in result.content


def test_invalid_doc_type_raises():
    payload = {**VALID_PAYLOAD, "doc_type": "manual_de_usuario"}
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="spec", text="documentar el login")

    with pytest.raises(ValueError, match="doc_type inválido"):
        DocumentacionAgent().run(intake, provider)


def test_empty_sections_raises():
    payload = {**VALID_PAYLOAD, "sections": []}
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="spec", text="documentar el login")

    with pytest.raises(ValueError, match="al menos una sección"):
        DocumentacionAgent().run(intake, provider)


def test_response_wrapped_in_markdown_fence_is_still_parsed():
    provider = FakeProvider(f"```json\n{json.dumps(VALID_PAYLOAD)}\n```")
    intake = Intake(source="spec", text="documentar el login")

    result = DocumentacionAgent().run(intake, provider)
    assert "Iniciar sesión con Google" in result.content
