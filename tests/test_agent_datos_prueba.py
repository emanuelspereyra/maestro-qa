import json

import pytest

from maestro_qa.agents.datos_prueba import AGENT_REGISTRY, DatosPruebaAgent
from maestro_qa.orchestrator import Intake

VALID_SPEC = {
    "dataset_id": "DS-USERS-001",
    "seed": 12345,
    "entities": [
        {
            "name": "users",
            "target": "dbo.users",
            "identifier_fields": ["id", "email"],
            "display_fields": ["username"],
            "sensitive_fields": [],
            "count": 2,
            "fields": {
                "id": {"type": "uuid"},
                "username": {"type": "username", "prefix": "qa"},
                "email": {"type": "email", "domain": "example.test"},
                "qa_run_id": {"type": "run_id"},
            },
        }
    ],
}


class FakeProvider:
    def __init__(self, response: str):
        self._response = response

    def complete(self, system, messages, **kwargs):
        return self._response


def test_registers_itself():
    assert isinstance(AGENT_REGISTRY["datos_prueba"], DatosPruebaAgent)


def test_valid_spec_generates_real_artifacts_on_disk(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    provider = FakeProvider(json.dumps(VALID_SPEC))
    intake = Intake(source="spec", text="necesito datos de usuarios de prueba")

    result = DatosPruebaAgent().run(intake, provider)

    assert result.agent == "datos_prueba"
    assert "DS-USERS-001" in result.content
    assert "GENERATED_NOT_INSERTED" in result.content
    assert "2 filas" in result.content

    dataset_path = tmp_path / "qa-artifacts" / "data" / "DS-USERS-001" / "dataset.json"
    assert dataset_path.exists()
    dataset = json.loads(dataset_path.read_text())
    assert len(dataset["entities"][0]["rows"]) == 2


def test_invalid_field_range_raises_with_real_script_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    broken_spec = json.loads(json.dumps(VALID_SPEC))
    broken_spec["entities"][0]["fields"]["age"] = {"type": "integer", "min": 50, "max": 10}
    provider = FakeProvider(json.dumps(broken_spec))
    intake = Intake(source="spec", text="necesito datos de usuarios de prueba")

    with pytest.raises(ValueError, match="min exceeds max"):
        DatosPruebaAgent().run(intake, provider)


def test_llm_response_wrapped_in_markdown_fence_is_still_parsed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    provider = FakeProvider(f"```json\n{json.dumps(VALID_SPEC)}\n```")
    intake = Intake(source="jira_ticket", text="datos de usuarios")

    result = DatosPruebaAgent().run(intake, provider)
    assert "DS-USERS-001" in result.content
