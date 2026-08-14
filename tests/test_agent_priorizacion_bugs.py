import json

import pytest

from maestro_qa.agents.priorizacion_bugs import AGENT_REGISTRY, PriorizacionBugsAgent
from maestro_qa.orchestrator import Intake

VALID_PAYLOAD = {
    "title": "El login con Google no redirige tras aceptar el consentimiento",
    "case_id_o_fuente": "FE-TC-001",
    "ambiente_y_versiones": "QA, commit abc123",
    "preconditions": ["Cuenta de Google válida"],
    "datos_usados": "DS-AUTH-001",
    "steps": ["Click en login con Google", "Aceptar el consentimiento"],
    "expected_result": "Redirige al dashboard autenticado",
    "actual_result": "Se queda en la pantalla de login sin sesión",
    "reproducibility": "siempre",
    "severity": "High",
    "business_priority": "pendiente de decisión de negocio",
    "evidence_required": ["screenshot", "network trace"],
}


class FakeProvider:
    def __init__(self, response: str):
        self._response = response

    def complete(self, system, messages, **kwargs):
        return self._response


def test_registers_itself():
    assert isinstance(AGENT_REGISTRY["priorizacion_bugs"], PriorizacionBugsAgent)


def test_valid_draft_includes_disclaimer_and_fields():
    provider = FakeProvider(json.dumps(VALID_PAYLOAD))
    intake = Intake(source="jira_ticket", text="el login con Google no redirige")

    result = PriorizacionBugsAgent().run(intake, provider)

    assert result.agent == "priorizacion_bugs"
    assert "Borrador sin duplicados verificados ni publicación real" in result.content
    assert "Severidad sugerida: High" in result.content
    assert "pendiente de decisión de negocio" in result.content


def test_invalid_severity_raises():
    payload = {**VALID_PAYLOAD, "severity": "Urgentisimo"}
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="spec", text="bug de login")

    with pytest.raises(ValueError, match="severity inválida"):
        PriorizacionBugsAgent().run(intake, provider)


def test_invalid_reproducibility_raises():
    payload = {**VALID_PAYLOAD, "reproducibility": "a veces"}
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="spec", text="bug de login")

    with pytest.raises(ValueError, match="reproducibility inválida"):
        PriorizacionBugsAgent().run(intake, provider)


def test_missing_field_raises():
    payload = dict(VALID_PAYLOAD)
    del payload["actual_result"]
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="spec", text="bug de login")

    with pytest.raises(ValueError, match="actual_result"):
        PriorizacionBugsAgent().run(intake, provider)


def test_response_wrapped_in_markdown_fence_is_still_parsed():
    provider = FakeProvider(f"```json\n{json.dumps(VALID_PAYLOAD)}\n```")
    intake = Intake(source="spec", text="bug de login")

    result = PriorizacionBugsAgent().run(intake, provider)
    assert "El login con Google" in result.content


def test_business_priority_is_always_forced_regardless_of_what_the_llm_returns():
    # bug real (auditoría 2026-08-14): _validate solo chequeaba que business_priority no
    # estuviera vacío, no que fuera EL literal fijo -- un LLM que ignorara la instrucción
    # y devolviera una prioridad real (ej. "Alta") se imprimía como si fuera legítima,
    # rompiendo en silencio la garantía de que este agente no decide prioridad de negocio.
    payload = {**VALID_PAYLOAD, "business_priority": "Alta"}
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="spec", text="bug de login")

    result = PriorizacionBugsAgent().run(intake, provider)

    assert "Alta" not in result.content
    assert "pendiente de decisión de negocio" in result.content
