from dataclasses import dataclass, field
from typing import Literal

from .agents.registry import AGENT_REGISTRY
from .providers import Provider

_DEFAULT_AGENTS = ["casos_manuales", "trazabilidad"]

# ponytail: routing por keyword, no por LLM — techo conocido, ver specs/002-orquestador.md
_KEYWORD_AGENTS = {
    "automatizacion": ["automatiz", "e2e", "ci/cd"],
    "datos_prueba": ["datos de prueba", "test data", "dataset", "carga masiva"],
    "priorizacion_bugs": ["bug", "defecto", "incidencia", "hotfix"],
    "documentacion": ["documentar", "documentación", "manual de usuario"],
    "regresion": ["regresión", "regression", "suite completa"],
    "performance": ["performance", "carga", "estrés", "latencia", "throughput"],
    "seguridad": ["seguridad", "vulnerabilidad", "owasp", "auth", "permisos"],
}

_RELEASE_READINESS = "release_readiness"


@dataclass
class Intake:
    source: Literal["jira_ticket", "spec"]
    text: str


@dataclass
class AgentResult:
    agent: str
    content: str
    error: bool = False


@dataclass
class RunResult:
    results: list[AgentResult] = field(default_factory=list)

    def to_markdown(self) -> str:
        if not self.results:
            return "Ningún agente registrado produjo resultados para este intake."
        sections = [f"## {r.agent}{' (error)' if r.error else ''}\n\n{r.content}" for r in self.results]
        return "\n\n".join(sections)


def classify_agents(intake: Intake) -> list[str]:
    text_lower = intake.text.lower()
    selected = list(_DEFAULT_AGENTS)
    for agent_name, keywords in _KEYWORD_AGENTS.items():
        if any(keyword in text_lower for keyword in keywords):
            selected.append(agent_name)
    return selected


def _run_agent(name: str, intake: Intake, provider: Provider) -> AgentResult:
    agent = AGENT_REGISTRY[name]
    try:
        return agent.run(intake, provider)
    except Exception as exc:  # noqa: BLE001 - un agente roto no debe tumbar a los demás
        return AgentResult(agent=name, content=str(exc), error=True)


def run(intake: Intake, provider: Provider) -> RunResult:
    selected = classify_agents(intake)
    results = [_run_agent(name, intake, provider) for name in selected if name in AGENT_REGISTRY]

    if _RELEASE_READINESS in AGENT_REGISTRY:
        readiness_intake = Intake(
            source=intake.source,
            text="\n\n".join(f"{r.agent}: {r.content}" for r in results),
        )
        results.append(_run_agent(_RELEASE_READINESS, readiness_intake, provider))

    return RunResult(results=results)
