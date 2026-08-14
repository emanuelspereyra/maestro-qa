import json

import pytest

from maestro_qa.agents.trazabilidad import AGENT_REGISTRY, TrazabilidadAgent
from maestro_qa.orchestrator import Intake

VALID_PAYLOAD = {
    "acceptance_criteria": [{"id": "AC-1", "text": "El usuario puede loguearse con Google"}],
    "traceability_matrix": [{"criterion_id": "AC-1", "case_ids": ["FE-TC-001"], "status": "covered"}],
    "untraceable_cases": [],
    "pending_items": [],
}


class FakeProvider:
    def __init__(self, response: str):
        self._response = response

    def complete(self, system, messages, **kwargs):
        return self._response


def test_registers_itself():
    assert isinstance(AGENT_REGISTRY["trazabilidad"], TrazabilidadAgent)


def test_valid_matrix_renders_covered_criteria():
    provider = FakeProvider(json.dumps(VALID_PAYLOAD))
    intake = Intake(source="jira_ticket", text="login con Google")

    result = TrazabilidadAgent().run(intake, provider)

    assert result.agent == "trazabilidad"
    assert "1 cubiertos, 0 huecos" in result.content
    assert "[covered] AC-1" in result.content
    assert "FE-TC-001" in result.content


def test_gap_without_generated_cases_is_reported_not_hidden():
    payload = {
        **VALID_PAYLOAD,
        "traceability_matrix": [{"criterion_id": "AC-1", "case_ids": [], "status": "gap"}],
    }
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="spec", text="login con Google")

    result = TrazabilidadAgent().run(intake, provider)

    assert "0 cubiertos, 1 huecos" in result.content
    assert "[gap] AC-1" in result.content


def test_untraceable_cases_are_surfaced():
    payload = {**VALID_PAYLOAD, "untraceable_cases": ["FE-TC-099"]}
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="spec", text="login con Google")

    result = TrazabilidadAgent().run(intake, provider)

    assert "FE-TC-099" in result.content
    assert "no trazables" in result.content


def test_invalid_status_raises():
    payload = {
        **VALID_PAYLOAD,
        "traceability_matrix": [{"criterion_id": "AC-1", "case_ids": [], "status": "parcial"}],
    }
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="spec", text="login con Google")

    with pytest.raises(ValueError, match="status inválido"):
        TrazabilidadAgent().run(intake, provider)


def test_empty_acceptance_criteria_raises():
    payload = {**VALID_PAYLOAD, "acceptance_criteria": []}
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="spec", text="login con Google")

    with pytest.raises(ValueError, match="acceptance_criteria"):
        TrazabilidadAgent().run(intake, provider)


def test_response_wrapped_in_markdown_fence_is_still_parsed():
    provider = FakeProvider(f"```json\n{json.dumps(VALID_PAYLOAD)}\n```")
    intake = Intake(source="spec", text="login con Google")

    result = TrazabilidadAgent().run(intake, provider)
    assert "AC-1" in result.content


def test_acceptance_criterion_missing_text_raises_clear_error_not_keyerror():
    # bug real (auditoría 2026-08-14): _validate no chequeaba que cada acceptance_criteria
    # tuviera "text", y run() accedía a c["text"] directo -> KeyError sin mensaje claro.
    payload = {**VALID_PAYLOAD, "acceptance_criteria": [{"id": "AC-1"}]}
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="spec", text="login con Google")

    with pytest.raises(ValueError, match="acceptance_criteria\\[0\\]"):
        TrazabilidadAgent().run(intake, provider)
