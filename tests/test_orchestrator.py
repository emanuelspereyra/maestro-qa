import pytest

from maestro_qa.agents.registry import AGENT_REGISTRY
from maestro_qa.orchestrator import AgentResult, Intake, classify_agents, run


class FakeAgent:
    def __init__(self, name, content="ok", raises=False, artifacts=None):
        self.name = name
        self.content = content
        self.raises = raises
        self.artifacts = artifacts or {}

    def run(self, intake, provider):
        if self.raises:
            raise RuntimeError(f"{self.name} broke")
        return AgentResult(agent=self.name, content=self.content, artifacts=self.artifacts)


@pytest.fixture
def clean_registry():
    original = dict(AGENT_REGISTRY)
    AGENT_REGISTRY.clear()
    yield AGENT_REGISTRY
    AGENT_REGISTRY.clear()
    AGENT_REGISTRY.update(original)


def test_default_agents_always_included():
    intake = Intake(source="spec", text="agregar un boton en el dashboard")
    selected = classify_agents(intake)
    assert "casos_manuales" in selected
    assert "trazabilidad" in selected


def test_keyword_routes_extra_agents():
    intake = Intake(source="jira_ticket", text="revisar vulnerabilidad OWASP en el login")
    selected = classify_agents(intake)
    assert "seguridad" in selected


def test_run_skips_agents_not_registered(clean_registry):
    intake = Intake(source="spec", text="cualquier cosa")
    result = run(intake, provider=None)
    assert result.results == []
    assert "Ningún agente" in result.to_markdown()


def test_run_captures_partial_failure_without_aborting(clean_registry):
    clean_registry["casos_manuales"] = FakeAgent("casos_manuales", raises=True)
    clean_registry["trazabilidad"] = FakeAgent("trazabilidad", content="cobertura ok")

    intake = Intake(source="spec", text="feature sin keywords")
    result = run(intake, provider=None)

    by_agent = {r.agent: r for r in result.results}
    assert by_agent["casos_manuales"].error is True
    assert by_agent["trazabilidad"].error is False
    assert by_agent["trazabilidad"].content == "cobertura ok"


def test_release_readiness_runs_last_with_aggregated_input(clean_registry):
    clean_registry["casos_manuales"] = FakeAgent("casos_manuales", content="3 casos")
    clean_registry["trazabilidad"] = FakeAgent("trazabilidad", content="100% cubierto")

    captured = {}

    class ReadinessAgent:
        def run(self, intake, provider):
            captured["text"] = intake.text
            return AgentResult(agent="release_readiness", content="go")

    clean_registry["release_readiness"] = ReadinessAgent()

    intake = Intake(source="spec", text="feature sin keywords")
    result = run(intake, provider=None)

    assert result.results[-1].agent == "release_readiness"
    assert "3 casos" in captured["text"]
    assert "100% cubierto" in captured["text"]


def test_casos_manuales_context_is_injected_into_other_agents(clean_registry):
    clean_registry["casos_manuales"] = FakeAgent(
        "casos_manuales", content="1 caso", artifacts={"cases": [{"case_id": "FE-TC-001"}]}
    )

    captured = {}

    class SpyAgent:
        def run(self, intake, provider):
            captured["text"] = intake.text
            return AgentResult(agent="seguridad", content="ok")

    clean_registry["seguridad"] = SpyAgent()

    intake = Intake(source="jira_ticket", text="revisar permisos de acceso")
    run(intake, provider=None)

    assert "Casos de prueba ya generados" in captured["text"]
    assert "FE-TC-001" in captured["text"]


def test_casos_manuales_error_does_not_inject_broken_context(clean_registry):
    clean_registry["casos_manuales"] = FakeAgent("casos_manuales", raises=True)

    captured = {}

    class SpyAgent:
        def run(self, intake, provider):
            captured["text"] = intake.text
            return AgentResult(agent="seguridad", content="ok")

    clean_registry["seguridad"] = SpyAgent()

    intake = Intake(source="jira_ticket", text="revisar permisos de acceso")
    run(intake, provider=None)

    assert captured["text"] == intake.text
    assert "Casos de prueba ya generados" not in captured["text"]


def test_adding_agent_needs_no_orchestrator_change(clean_registry):
    clean_registry["casos_manuales"] = FakeAgent("casos_manuales")
    clean_registry["trazabilidad"] = FakeAgent("trazabilidad")
    clean_registry["seguridad"] = FakeAgent("seguridad", content="sin hallazgos")

    intake = Intake(source="jira_ticket", text="revisar permisos de acceso")
    result = run(intake, provider=None)

    assert {r.agent for r in result.results} == {"casos_manuales", "trazabilidad", "seguridad"}
