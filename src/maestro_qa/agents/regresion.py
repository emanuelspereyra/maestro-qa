import json
import re

from ..orchestrator import AgentResult, Intake
from ..providers import Provider
from .registry import AGENT_REGISTRY

_VALID_PRIORITIES = {"full", "targeted", "smoke"}

_SYSTEM_PROMPT = """Sos un agente de QA que arma un PLAN de regresión a partir de un \
ticket que describe un cambio — no generás casos nuevos (eso es trabajo de otro agente) ni \
ejecutás nada (no hay runner conectado).

Identificá las áreas que cambiaron (endpoints, rutas, modelos, módulos) según el ticket.

Si el mensaje incluye una sección "Casos de prueba ya generados", cruzá cada caso contra \
esas áreas: si el caso toca algo que cambió, marcalo en `affected_cases` con el motivo. Si \
un área cambiada no tiene ningún caso que la cubra, reportalo en `coverage_gaps` — no \
inventes un caso ahí, no es tu trabajo.

Sugerí `regression_priority`: "full" (cambio amplio o de alto riesgo, correr toda la \
suite), "targeted" (cambio acotado, correr solo lo afectado), "smoke" (cambio cosmético o \
de bajo riesgo, alcanza un smoke test).

Devolvé EXCLUSIVAMENTE un objeto JSON (sin texto adicional, sin markdown) con estos campos:
{
  "changed_areas": ["..."],
  "affected_cases": [{"case_id": "...", "reason": "..."}],
  "coverage_gaps": ["áreas cambiadas sin ningún caso que las cubra, puede estar vacía"],
  "regression_priority": "full|targeted|smoke",
  "pending_items": ["información faltante sobre el cambio, puede estar vacía"]
}
"""


def _extract_json_object(text: str) -> str:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("La respuesta del LLM no contiene un objeto JSON")
    return match.group(0)


def _validate(payload: dict[str, object]) -> None:
    changed_areas = payload.get("changed_areas")
    if not isinstance(changed_areas, list) or not changed_areas:
        raise ValueError("changed_areas no puede estar vacío")
    if payload.get("regression_priority") not in _VALID_PRIORITIES:
        raise ValueError(
            f"regression_priority inválida: {payload.get('regression_priority')!r}, "
            f"debe ser una de {sorted(_VALID_PRIORITIES)}"
        )
    affected_cases = payload.get("affected_cases")
    if not isinstance(affected_cases, list):
        raise ValueError("affected_cases debe ser una lista")  # noqa: TRY004
    for index, case in enumerate(affected_cases):
        if not case.get("case_id") or not case.get("reason"):
            raise ValueError(f"affected_cases[{index}]: case_id y reason no pueden estar vacíos")


class RegresionAgent:
    def run(self, intake: Intake, provider: Provider) -> AgentResult:
        raw = provider.complete(system=_SYSTEM_PROMPT, messages=[{"role": "user", "content": intake.text}])
        payload = json.loads(_extract_json_object(raw))
        _validate(payload)

        affected = payload["affected_cases"]
        affected_text = (
            "\n".join(f"- {c['case_id']}: {c['reason']}" for c in affected) if affected else "Ninguno todavía."
        )
        gaps = payload.get("coverage_gaps") or []
        gaps_text = "\n".join(f"- {gap}" for gap in gaps) if gaps else "Ninguno."

        content = (
            f"Prioridad de regresión: {payload['regression_priority']}\n\n"
            f"Áreas cambiadas: {', '.join(payload['changed_areas'])}\n\n"
            f"Casos afectados:\n{affected_text}\n\n"
            f"Huecos de cobertura:\n{gaps_text}"
        )
        pending = payload.get("pending_items") or []
        if pending:
            content += "\n\nPendiente:\n" + "\n".join(f"- {item}" for item in pending)

        return AgentResult(agent="regresion", content=content)


AGENT_REGISTRY["regresion"] = RegresionAgent()
