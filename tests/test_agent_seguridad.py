import json

import pytest

from maestro_qa.agents.seguridad import AGENT_REGISTRY, SeguridadAgent
from maestro_qa.orchestrator import Intake

VALID_CASE = {
    "category": "broken-access-control",
    "title": "Un usuario no puede leer el perfil de otro cambiando el ID",
    "objective": "Verificar autorización a nivel de objeto",
    "steps": ["Loguearse como usuario A", "Solicitar GET /users/<id-de-B>"],
    "expected_result": "La API responde 403 sin exponer datos de B",
    "severity_if_fails": "High",
}


class FakeProvider:
    def __init__(self, response: str):
        self._response = response

    def complete(self, system, messages, **kwargs):
        return self._response


def test_registers_itself():
    assert isinstance(AGENT_REGISTRY["seguridad"], SeguridadAgent)


def test_valid_cases_render_with_severity_and_expected_result():
    payload = {"cases": [VALID_CASE], "pending_items": []}
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="jira_ticket", text="revisar permisos al ver el perfil de otro usuario")

    result = SeguridadAgent().run(intake, provider)

    assert result.agent == "seguridad"
    assert "[broken-access-control]" in result.content
    assert "Severidad si falla: High" in result.content
    assert "comportamiento seguro" in result.content


def test_pending_categories_are_surfaced_not_invented():
    payload = {"cases": [VALID_CASE], "pending_items": ["Falta saber si hay rate limiting configurado"]}
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="spec", text="revisar permisos")

    result = SeguridadAgent().run(intake, provider)

    assert "Falta saber si hay rate limiting configurado" in result.content


def test_invalid_category_raises():
    payload = {"cases": [{**VALID_CASE, "category": "csrf-clasico"}], "pending_items": []}
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="spec", text="revisar permisos")

    with pytest.raises(ValueError, match="category inválida"):
        SeguridadAgent().run(intake, provider)


def test_invalid_severity_raises():
    payload = {"cases": [{**VALID_CASE, "severity_if_fails": "Catastrofico"}], "pending_items": []}
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="spec", text="revisar permisos")

    with pytest.raises(ValueError, match="severity_if_fails inválida"):
        SeguridadAgent().run(intake, provider)


def test_empty_cases_raises():
    payload = {"cases": [], "pending_items": []}
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="spec", text="revisar permisos")

    with pytest.raises(ValueError, match="al menos un caso"):
        SeguridadAgent().run(intake, provider)


def test_response_wrapped_in_markdown_fence_is_still_parsed():
    payload = {"cases": [VALID_CASE], "pending_items": []}
    provider = FakeProvider(f"```json\n{json.dumps(payload)}\n```")
    intake = Intake(source="spec", text="revisar permisos")

    result = SeguridadAgent().run(intake, provider)
    assert "broken-access-control" in result.content
