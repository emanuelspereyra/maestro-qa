import json

import pytest

from maestro_qa import writers
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
    assert result.artifacts["cases"] == cases


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


class StubWriter:
    def __init__(self, raise_for=frozenset()):
        self._raise_for = raise_for

    def create(self, item):
        if item.external_ref in self._raise_for:
            raise writers.WriterError(f"fallo simulado para {item.external_ref}")
        return writers.WriteResult(external_id="123", url=f"https://example.test/{item.external_ref}")


def test_without_writer_configured_no_publish_sections_appear(monkeypatch):
    monkeypatch.setattr(writers, "get_writer", lambda: None)
    cases = [_case("happy-path", "FE-TC-001")]
    provider = FakeProvider(json.dumps(cases))
    intake = Intake(source="spec", text="crear usuario")

    result = CasosManualesAgent().run(intake, provider)

    assert "Casos publicados" not in result.content
    assert "## Pendiente" not in result.content


def test_publishes_each_case_when_writer_is_configured(monkeypatch):
    monkeypatch.setattr(writers, "get_writer", lambda: StubWriter())
    cases = [_case("happy-path", "FE-TC-001"), _case("unhappy-path", "FE-TC-002")]
    provider = FakeProvider(json.dumps(cases))
    intake = Intake(source="spec", text="crear usuario")

    result = CasosManualesAgent().run(intake, provider)

    assert "## Casos publicados" in result.content
    assert "FE-TC-001: https://example.test/FE-TC-001" in result.content
    assert "FE-TC-002: https://example.test/FE-TC-002" in result.content


def test_one_case_failing_to_publish_does_not_block_the_others(monkeypatch):
    monkeypatch.setattr(writers, "get_writer", lambda: StubWriter(raise_for={"FE-TC-002"}))
    cases = [_case("happy-path", "FE-TC-001"), _case("unhappy-path", "FE-TC-002")]
    provider = FakeProvider(json.dumps(cases))
    intake = Intake(source="spec", text="crear usuario")

    result = CasosManualesAgent().run(intake, provider)

    assert "FE-TC-001: https://example.test/FE-TC-001" in result.content
    assert "FE-TC-002: no se pudo publicar" in result.content
    assert result.artifacts["cases"] == cases  # el resto del pipeline sigue viendo los casos igual


def test_writer_misconfiguration_is_reported_without_crashing_the_agent(monkeypatch):
    def raise_misconfigured():
        raise ValueError("Faltan variables de entorno para MAESTRO_WRITER=azure_devops: MAESTRO_AZURE_DEVOPS_PAT.")

    monkeypatch.setattr(writers, "get_writer", raise_misconfigured)
    cases = [_case("happy-path", "FE-TC-001")]
    provider = FakeProvider(json.dumps(cases))
    intake = Intake(source="spec", text="crear usuario")

    result = CasosManualesAgent().run(intake, provider)

    assert "No se pudo configurar el writer" in result.content
    assert result.artifacts["cases"] == cases


def test_early_error_format_from_validate_cases_raises_value_error_not_key_error(monkeypatch):
    """validate_cases.py returns early-error format {"valid": false, "error": "..."}
    on file not found / JSON decode error / ValueError. The agent must raise ValueError
    with the error message, NOT KeyError on 'delivery_status'."""
    import subprocess

    early_error_report = json.dumps({"valid": False, "error": "No such file or directory: '/tmp/missing.json'"})

    def mock_run(cmd, **kwargs):
        # First call is validate_cases.py — return early-error format
        if "validate_cases" in str(cmd[1]):
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=2,
                stdout=early_error_report,
                stderr="",
            )
        # Second call is render_manual_cases.py — should not be reached
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", mock_run)
    cases = [_case("happy-path", "FE-TC-001")]
    provider = FakeProvider(json.dumps(cases))
    intake = Intake(source="spec", text="crear usuario")

    with pytest.raises(ValueError, match="error temprano"):
        CasosManualesAgent().run(intake, provider)
