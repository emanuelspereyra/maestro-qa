import json

import pytest

from maestro_qa.agents.regresion import AGENT_REGISTRY, RegresionAgent
from maestro_qa.orchestrator import Intake

VALID_PAYLOAD = {
    "change_description": "Se agregó login con Google además del login por email/password",
    "regression_scope": "targeted",
    "affected_areas": ["autenticación", "gestión de sesión"],
    "priority_areas": [
        {
            "area": "autenticación",
            "reason": "Nuevo flujo de login que puede romper el existente",
            "scenario_families_to_recheck": ["happy-path", "unhappy-path"],
        }
    ],
    "out_of_scope_areas": [],
    "pending_items": [],
}


class FakeProvider:
    def __init__(self, response: str):
        self._response = response

    def complete(self, system, messages, **kwargs):
        return self._response


def test_registers_itself():
    assert isinstance(AGENT_REGISTRY["regresion"], RegresionAgent)


def test_valid_plan_renders_scope_and_priority_areas():
    provider = FakeProvider(json.dumps(VALID_PAYLOAD))
    intake = Intake(source="jira_ticket", text="agregamos login con Google, correr regresión")

    result = RegresionAgent().run(intake, provider)

    assert result.agent == "regresion"
    assert "**targeted**" in result.content
    assert "autenticación" in result.content


def test_pending_items_are_surfaced_not_hidden():
    payload = {**VALID_PAYLOAD, "pending_items": ["Falta saber si el módulo de pagos depende de la sesión"]}
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="spec", text="regresión del login")

    result = RegresionAgent().run(intake, provider)

    assert "Falta saber si el módulo de pagos depende de la sesión" in result.content


def test_invalid_scope_raises():
    payload = {**VALID_PAYLOAD, "regression_scope": "maxima"}
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="spec", text="regresión del login")

    with pytest.raises(ValueError, match="regression_scope inválido"):
        RegresionAgent().run(intake, provider)


def test_empty_priority_areas_raises():
    payload = {**VALID_PAYLOAD, "priority_areas": []}
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="spec", text="regresión del login")

    with pytest.raises(ValueError, match="al menos un área prioritaria"):
        RegresionAgent().run(intake, provider)


def test_response_wrapped_in_markdown_fence_is_still_parsed():
    provider = FakeProvider(f"```json\n{json.dumps(VALID_PAYLOAD)}\n```")
    intake = Intake(source="spec", text="regresión del login")

    result = RegresionAgent().run(intake, provider)
    assert "targeted" in result.content
