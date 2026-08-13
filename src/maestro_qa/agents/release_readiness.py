import json
import re

from ..orchestrator import AgentResult, Intake
from ..providers import Provider
from .registry import AGENT_REGISTRY

_VALID_STATUSES = {"GO", "GO_WITH_CONDITIONS", "NO_GO"}
_ERROR_HEADER = re.compile(r"^Agentes con error: (.+)$", re.MULTILINE)

_SYSTEM_PROMPT = """Sos un agente de QA que lee el resumen de lo que hicieron todos los \
demás agentes en este run y da un veredicto de release-readiness — no inventás detalles \
que no estén en el resumen; si el resumen es escueto, decilo.

Devolvé EXCLUSIVAMENTE un objeto JSON (sin texto adicional, sin markdown) con estos campos:
{
  "overall_status": "GO|GO_WITH_CONDITIONS|NO_GO",
  "summary": "...",
  "blocking_issues": ["puede estar vacía"],
  "non_blocking_notes": ["puede estar vacía"]
}
"""


def _extract_json_object(text: str) -> str:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("La respuesta del LLM no contiene un objeto JSON")
    return match.group(0)


def _validate(payload: dict[str, object]) -> None:
    if payload.get("overall_status") not in _VALID_STATUSES:
        raise ValueError(
            f"overall_status inválido: {payload.get('overall_status')!r}, "
            f"debe ser uno de {sorted(_VALID_STATUSES)}"
        )
    if not payload.get("summary"):
        raise ValueError("summary no puede estar vacío")


def _error_agents_from_header(text: str) -> list[str]:
    match = _ERROR_HEADER.search(text)
    if not match or match.group(1).strip() == "ninguno":
        return []
    return [name.strip() for name in match.group(1).split(",")]


class ReleaseReadinessAgent:
    def run(self, intake: Intake, provider: Provider) -> AgentResult:
        raw = provider.complete(system=_SYSTEM_PROMPT, messages=[{"role": "user", "content": intake.text}])
        payload = json.loads(_extract_json_object(raw))
        _validate(payload)

        # ponytail: el encabezado "Agentes con error: ..." lo arma el orquestador, no el
        # LLM — es determinístico, así que corregimos acá en vez de confiar en que el LLM
        # lo haya notado en medio del resumen en texto libre. Ver specs/019.
        error_agents = _error_agents_from_header(intake.text)
        overall_status = payload["overall_status"]
        notes = list(payload.get("non_blocking_notes") or [])
        if error_agents and overall_status == "GO":
            overall_status = "NO_GO"
            notes.append(f"Corregido a NO_GO: {len(error_agents)} agente(s) fallaron en este run ({', '.join(error_agents)}).")

        blocking = payload.get("blocking_issues") or []
        content = (
            f"Veredicto: {overall_status}\n\n"
            f"{payload['summary']}\n\n"
            f"Bloqueantes:\n" + ("\n".join(f"- {item}" for item in blocking) if blocking else "Ninguno.") + "\n\n"
            "Notas:\n" + ("\n".join(f"- {item}" for item in notes) if notes else "Ninguna.")
        )
        return AgentResult(agent="release_readiness", content=content)


AGENT_REGISTRY["release_readiness"] = ReleaseReadinessAgent()
