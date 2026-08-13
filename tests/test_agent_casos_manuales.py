import json

import pytest

from maestro_qa.agents.casos_manuales import AGENT_REGISTRY, CasosManualesAgent
from maestro_qa.orchestrator import Intake

VALID_CASE = {
    "case_id": "FE-TC-001",
    "feature_id": "users.create",
    "layer": "frontend",
    "scenario_family": "happy-path",
    "business_rule_ids": ["BR-USERS-001"],
    "coverage_dimensions": ["authorized-role"],
    "title": "Crear usuario válido",
    "objective": "Verificar el flujo visible de creación",
    "sources": ["REQ-001"],
    "work_item_ids": [],
    "confidence": "confirmed",
    "priority": "high",
    "execution_type": "both",
    "preconditions": ["Ambiente QA disponible"],
    "steps": [{"order": 1, "action": "Abrir el formulario", "expected": "Se muestra"}],
    "expected_result": "El usuario queda creado",
    "actual_result": "Pendiente",
    "status": "NOT_EXECUTED",
    "data_contract": {
        "dataset_id": "DS-USERS-001",
        "requirements": ["Usuario único"],
        "setup_method": "api",
        "cleanup_method": "api",
    },
    "evidence_required": ["screenshot"],
}


def _case(scenario_family: str, case_id: str) -> dict:
    return {**VALID_CASE, "case_id": case_id, "scenario_family": scenario_family}


class FakeProvider:
    def __init__(self, response: str):
        self._response = response

    def complete(self, system, messages, **kwargs):
        return self._response


def test_registers_itself():
    assert isinstance(AGENT_REGISTRY["casos_manuales"], CasosManualesAgent)


def test_valid_cases_produce_result_with_summary_and_render():
    cases = [
        _case("happy-path", "FE-TC-001"),
        _case("unhappy-path", "FE-TC-002"),
        _case("boundary", "FE-TC-003"),
    ]
    provider = FakeProvider(json.dumps(cases))
    intake = Intake(source="spec", text="crear usuario")

    result = CasosManualesAgent().run(intake, provider)

    assert result.agent == "casos_manuales"
    assert "Cobertura:" in result.content
    assert "Crear usuario válido" in result.content


def test_invalid_cases_raise_with_validation_errors():
    broken_case = dict(VALID_CASE)
    del broken_case["steps"]
    provider = FakeProvider(json.dumps([broken_case]))
    intake = Intake(source="spec", text="crear usuario")

    with pytest.raises(ValueError, match="steps"):
        CasosManualesAgent().run(intake, provider)


def test_llm_response_wrapped_in_markdown_fence_is_still_parsed():
    cases = [_case("happy-path", "FE-TC-001")]
    provider = FakeProvider(f"```json\n{json.dumps(cases)}\n```")
    intake = Intake(source="jira_ticket", text="crear usuario")

    result = CasosManualesAgent().run(intake, provider)
    assert "Cobertura:" in result.content
