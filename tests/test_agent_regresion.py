import json

import pytest

from maestro_qa.agents.regresion import AGENT_REGISTRY, RegresionAgent
from maestro_qa.orchestrator import Intake

VALID_PAYLOAD = {
    "changed_areas": ["POST /auth/google/callback"],
    "affected_cases": [{"case_id": "BE-TC-001", "reason": "Toca el mismo endpoint de callback"}],
    "coverage_gaps": [],
    "regression_priority": "targeted",
    "pending_items": [],
}


class FakeProvider:
    def __init__(self, response: str):
        self._response = response

    def complete(self, system, messages, **kwargs):
        return self._response


def test_registers_itself():
    assert isinstance(AGENT_REGISTRY["regresion"], RegresionAgent)


def test_valid_plan_renders_priority_and_affected_cases():
    provider = FakeProvider(json.dumps(VALID_PAYLOAD))
    intake = Intake(source="jira_ticket", text="se modificó el endpoint de login con Google")

    result = RegresionAgent().run(intake, provider)

    assert result.agent == "regresion"
    assert "Prioridad de regresión: targeted" in result.content
    assert "BE-TC-001: Toca el mismo endpoint de callback" in result.content


def test_coverage_gaps_are_surfaced_not_invented():
    payload = {**VALID_PAYLOAD, "coverage_gaps": ["No hay ningún caso para el manejo de token expirado"]}
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="spec", text="cambio en el login")

    result = RegresionAgent().run(intake, provider)

    assert "No hay ningún caso para el manejo de token expirado" in result.content


def test_no_affected_cases_is_reported_not_hidden():
    payload = {**VALID_PAYLOAD, "affected_cases": []}
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="spec", text="cambio menor de estilos")

    result = RegresionAgent().run(intake, provider)

    assert "Ninguno todavía." in result.content


def test_invalid_priority_raises():
    payload = {**VALID_PAYLOAD, "regression_priority": "urgente"}
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="spec", text="cambio en el login")

    with pytest.raises(ValueError, match="regression_priority inválida"):
        RegresionAgent().run(intake, provider)


def test_empty_changed_areas_raises():
    payload = {**VALID_PAYLOAD, "changed_areas": []}
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="spec", text="cambio en el login")

    with pytest.raises(ValueError, match="changed_areas"):
        RegresionAgent().run(intake, provider)


def test_response_wrapped_in_markdown_fence_is_still_parsed():
    provider = FakeProvider(f"```json\n{json.dumps(VALID_PAYLOAD)}\n```")
    intake = Intake(source="spec", text="cambio en el login")

    result = RegresionAgent().run(intake, provider)
    assert "targeted" in result.content
