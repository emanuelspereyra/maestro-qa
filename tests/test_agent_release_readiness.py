import json

import pytest

from maestro_qa.agents.release_readiness import AGENT_REGISTRY, ReleaseReadinessAgent
from maestro_qa.orchestrator import Intake

VALID_PAYLOAD = {
    "overall_status": "GO",
    "summary": "Todos los agentes corrieron sin errores y no hay bloqueantes.",
    "blocking_issues": [],
    "non_blocking_notes": [],
}


class FakeProvider:
    def __init__(self, response: str):
        self._response = response

    def complete(self, system, messages, **kwargs):
        return self._response


def test_registers_itself():
    assert isinstance(AGENT_REGISTRY["release_readiness"], ReleaseReadinessAgent)


def test_go_without_errors_stays_go():
    provider = FakeProvider(json.dumps(VALID_PAYLOAD))
    intake = Intake(source="spec", text="Agentes con error: ninguno\n\ncasos_manuales: 3 casos")

    result = ReleaseReadinessAgent().run(intake, provider)

    assert result.agent == "release_readiness"
    assert "Veredicto: GO" in result.content
    assert "NO_GO" not in result.content


def test_go_with_reported_errors_is_corrected_to_no_go():
    provider = FakeProvider(json.dumps(VALID_PAYLOAD))
    intake = Intake(
        source="spec",
        text="Agentes con error: casos_manuales\n\ncasos_manuales (ERROR): boom",
    )

    result = ReleaseReadinessAgent().run(intake, provider)

    assert "Veredicto: NO_GO" in result.content
    assert "Corregido a NO_GO" in result.content
    assert "casos_manuales" in result.content


def test_no_go_with_errors_is_left_as_is():
    payload = {**VALID_PAYLOAD, "overall_status": "NO_GO", "blocking_issues": ["El login está roto"]}
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="spec", text="Agentes con error: casos_manuales\n\ncasos_manuales (ERROR): boom")

    result = ReleaseReadinessAgent().run(intake, provider)

    assert "Veredicto: NO_GO" in result.content
    assert "El login está roto" in result.content
    assert "Corregido a NO_GO" not in result.content


def test_invalid_status_raises():
    payload = {**VALID_PAYLOAD, "overall_status": "QUIZAS"}
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="spec", text="Agentes con error: ninguno\n\ncasos_manuales: ok")

    with pytest.raises(ValueError, match="overall_status inválido"):
        ReleaseReadinessAgent().run(intake, provider)


def test_empty_summary_raises():
    payload = {**VALID_PAYLOAD, "summary": ""}
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="spec", text="Agentes con error: ninguno\n\ncasos_manuales: ok")

    with pytest.raises(ValueError, match="summary"):
        ReleaseReadinessAgent().run(intake, provider)


def test_response_wrapped_in_markdown_fence_is_still_parsed():
    provider = FakeProvider(f"```json\n{json.dumps(VALID_PAYLOAD)}\n```")
    intake = Intake(source="spec", text="Agentes con error: ninguno\n\ncasos_manuales: ok")

    result = ReleaseReadinessAgent().run(intake, provider)
    assert "Veredicto: GO" in result.content
