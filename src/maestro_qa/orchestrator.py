import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from . import vendor_bundle
from .agents.registry import AGENT_REGISTRY
from .providers import Provider

_PROJECT = "maestro-qa"

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


def _history_call(history_dir: Path, *args: str) -> dict[str, object]:
    script = vendor_bundle.scripts_dir() / "qa_history.py"
    result = subprocess.run(
        ["python3", str(script), *args, "--history-dir", str(history_dir)],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)  # type: ignore[no-any-return]


# ponytail: el historial es auditoría, no el trabajo real — si qa_history.py falla
# o no está disponible, run() sigue funcionando igual. Ver specs/006 backlog.
def _start_history(history_dir: Path, intake: Intake) -> str | None:
    try:
        response = _history_call(
            history_dir, "start-run", "--project", _PROJECT, "--summary", intake.text[:200]
        )
        return str(response["run_id"])
    except Exception:  # noqa: BLE001
        return None


def _log_history(history_dir: Path, run_id: str, result: AgentResult) -> None:
    try:
        _history_call(
            history_dir,
            "log",
            "--run-id",
            run_id,
            "--module",
            result.agent,
            "--action",
            "run",
            "--status",
            "FAILED" if result.error else "EXECUTED",
            "--summary",
            result.content[:200],
        )
    except Exception:  # noqa: BLE001, S110
        pass


def _end_history(history_dir: Path, run_id: str) -> None:
    try:
        _history_call(history_dir, "end-run", "--run-id", run_id, "--status", "COMPLETED")
    except Exception:  # noqa: BLE001, S110
        pass


def run(intake: Intake, provider: Provider, history_dir: Path | None = None) -> RunResult:
    selected = classify_agents(intake)
    run_id = _start_history(history_dir, intake) if history_dir else None

    results = [_run_agent(name, intake, provider) for name in selected if name in AGENT_REGISTRY]
    if run_id and history_dir:
        for result in results:
            _log_history(history_dir, run_id, result)

    if _RELEASE_READINESS in AGENT_REGISTRY:
        readiness_intake = Intake(
            source=intake.source,
            text="\n\n".join(f"{r.agent}: {r.content}" for r in results),
        )
        readiness_result = _run_agent(_RELEASE_READINESS, readiness_intake, provider)
        results.append(readiness_result)
        if run_id and history_dir:
            _log_history(history_dir, run_id, readiness_result)

    if run_id and history_dir:
        _end_history(history_dir, run_id)

    return RunResult(results=results)
