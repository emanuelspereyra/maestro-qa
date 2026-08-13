import json

import pytest

from maestro_qa import sonarqube, sonarqube_runtime
from maestro_qa.agents import seguridad
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
        self.received_messages: list[str] = []

    def complete(self, system, messages, **kwargs):
        self.received_messages.append(messages[0]["content"])
        return self._response


def _set_sonarqube_env(monkeypatch):
    monkeypatch.setenv("MAESTRO_SONARQUBE_URL", "https://sonar.example.test")
    monkeypatch.setenv("MAESTRO_SONARQUBE_TOKEN", "token123")
    monkeypatch.setenv("MAESTRO_SONARQUBE_PROJECT_KEY", "my-project")


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


def test_sonarqube_context_is_injected_when_configured_and_findings_exist(monkeypatch):
    _set_sonarqube_env(monkeypatch)
    monkeypatch.setattr(
        seguridad.sonarqube,
        "fetch_findings",
        lambda *a, **kw: {
            "vulnerabilities": [{"severity": "CRITICAL", "message": "SQLi", "component": "x", "line": 1}],
            "hotspots": [],
        },
    )
    payload = {"cases": [VALID_CASE], "pending_items": []}
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="jira_ticket", text="revisar permisos")

    SeguridadAgent().run(intake, provider)

    assert "Hallazgos reales de SonarQube" in provider.received_messages[0]
    assert "SQLi" in provider.received_messages[0]


def test_without_env_vars_behaves_exactly_as_before():
    payload = {"cases": [VALID_CASE], "pending_items": []}
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="spec", text="revisar permisos")

    SeguridadAgent().run(intake, provider)

    assert provider.received_messages[0] == "revisar permisos"


def test_sonarqube_failure_does_not_break_case_generation(monkeypatch):
    _set_sonarqube_env(monkeypatch)

    def raise_error(*args, **kwargs):
        raise sonarqube.SonarQubeError("servidor caído")

    monkeypatch.setattr(seguridad.sonarqube, "fetch_findings", raise_error)
    payload = {"cases": [VALID_CASE], "pending_items": []}
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="spec", text="revisar permisos")

    result = SeguridadAgent().run(intake, provider)

    assert result.agent == "seguridad"
    assert provider.received_messages[0] == "revisar permisos"


def test_ephemeral_mode_runs_scan_and_injects_findings(monkeypatch):
    monkeypatch.setenv("MAESTRO_SONARQUBE_EPHEMERAL", "true")
    monkeypatch.setenv("MAESTRO_SONARQUBE_SCAN_PATH", "/tmp/some-repo")
    monkeypatch.setenv("MAESTRO_SONARQUBE_PROJECT_KEY", "my-project")
    monkeypatch.setattr(
        seguridad.sonarqube_runtime,
        "run_ephemeral_scan",
        lambda repo_path, project_key: {
            "vulnerabilities": [{"severity": "CRITICAL", "message": "SQLi", "component": "x", "line": 1}],
            "hotspots": [],
        },
    )
    payload = {"cases": [VALID_CASE], "pending_items": []}
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="jira_ticket", text="revisar permisos")

    SeguridadAgent().run(intake, provider)

    assert "Hallazgos reales de SonarQube" in provider.received_messages[0]
    assert "SQLi" in provider.received_messages[0]


def test_ephemeral_mode_failure_does_not_break_case_generation(monkeypatch):
    monkeypatch.setenv("MAESTRO_SONARQUBE_EPHEMERAL", "true")
    monkeypatch.setenv("MAESTRO_SONARQUBE_SCAN_PATH", "/tmp/some-repo")
    monkeypatch.setenv("MAESTRO_SONARQUBE_PROJECT_KEY", "my-project")

    def raise_error(repo_path, project_key):
        raise sonarqube_runtime.SonarQubeRuntimeError("docker no disponible")

    monkeypatch.setattr(seguridad.sonarqube_runtime, "run_ephemeral_scan", raise_error)
    payload = {"cases": [VALID_CASE], "pending_items": []}
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="spec", text="revisar permisos")

    result = SeguridadAgent().run(intake, provider)

    assert result.agent == "seguridad"
    assert provider.received_messages[0] == "revisar permisos"


def test_ephemeral_mode_without_scan_path_falls_back_silently(monkeypatch):
    monkeypatch.setenv("MAESTRO_SONARQUBE_EPHEMERAL", "true")
    monkeypatch.delenv("MAESTRO_SONARQUBE_SCAN_PATH", raising=False)
    payload = {"cases": [VALID_CASE], "pending_items": []}
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="spec", text="revisar permisos")

    result = SeguridadAgent().run(intake, provider)

    assert result.agent == "seguridad"
    assert provider.received_messages[0] == "revisar permisos"


def test_response_wrapped_in_markdown_fence_is_still_parsed():
    payload = {"cases": [VALID_CASE], "pending_items": []}
    provider = FakeProvider(f"```json\n{json.dumps(payload)}\n```")
    intake = Intake(source="spec", text="revisar permisos")

    result = SeguridadAgent().run(intake, provider)
    assert "broken-access-control" in result.content
