import json
import re

from ..orchestrator import AgentResult, Intake
from ..providers import Provider
from .registry import AGENT_REGISTRY

_VALID_SCOPES = {"full", "targeted", "smoke"}

_SYSTEM_PROMPT = """Sos un agente de QA que redacta un PLAN de regresión a partir de un \
cambio descrito en un ticket — no seleccionás casos de una suite existente (todavía no hay \
una biblioteca de casos persistida), armás un plan por área/alcance.

Identificá las áreas de la aplicación afectadas por el cambio y recomendá un \
`regression_scope`: full (el cambio es riesgoso o transversal, correr toda la suite), \
targeted (afecta áreas específicas, correr regresión solo ahí) o smoke (cambio de bajo \
riesgo, alcanza un smoke test). Para cada área prioritaria, indicá qué familias de \
escenario conviene re-chequear (happy-path, unhappy-path, boundary, authorization, \
data-integrity, etc. — las de comprehensive-coverage.md).

Si el mensaje incluye una sección "Casos de prueba ya generados", citalos explícitamente \
como parte del área afectada (por `case_id` o `feature_id`) — no inventes una selección de \
una suite que no existe.

Devolvé EXCLUSIVAMENTE un objeto JSON (sin texto adicional, sin markdown) con estos campos:
{
  "change_description": "...",
  "regression_scope": "full|targeted|smoke",
  "affected_areas": ["..."],
  "priority_areas": [
    {"area": "...", "reason": "...", "scenario_families_to_recheck": ["..."]}
  ],
  "out_of_scope_areas": ["área no afectada, con motivo — puede estar vacía"],
  "pending_items": ["información faltante sobre el alcance real del cambio, puede estar vacía"]
}
"""


def _extract_json_object(text: str) -> str:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("La respuesta del LLM no contiene un objeto JSON")
    return match.group(0)


def _validate(payload: dict[str, object]) -> None:
    if payload.get("regression_scope") not in _VALID_SCOPES:
        raise ValueError(
            f"regression_scope inválido: {payload.get('regression_scope')!r}, "
            f"debe ser uno de {sorted(_VALID_SCOPES)}"
        )
    if not payload.get("affected_areas"):
        raise ValueError("El plan debe incluir al menos un área afectada")
    priority_areas = payload.get("priority_areas")
    if not isinstance(priority_areas, list) or not priority_areas:
        raise ValueError("El plan debe incluir al menos un área prioritaria")
    for index, area in enumerate(priority_areas):
        if not area.get("area") or not area.get("reason"):
            raise ValueError(f"priority_areas[{index}]: area y reason no pueden estar vacíos")


class RegresionAgent:
    def run(self, intake: Intake, provider: Provider) -> AgentResult:
        raw = provider.complete(system=_SYSTEM_PROMPT, messages=[{"role": "user", "content": intake.text}])
        payload = json.loads(_extract_json_object(raw))
        _validate(payload)

        priority_lines = "\n".join(
            f"- {a['area']}: {a['reason']} (re-chequear: {', '.join(a.get('scenario_families_to_recheck') or [])})"
            for a in payload["priority_areas"]
        )
        content = (
            f"Alcance de regresión recomendado: **{payload['regression_scope']}**\n\n"
            f"Cambio: {payload['change_description']}\n\n"
            f"Áreas afectadas: {', '.join(payload['affected_areas'])}\n\n"
            f"Prioridades:\n{priority_lines}"
        )

        out_of_scope = payload.get("out_of_scope_areas") or []
        if out_of_scope:
            content += "\n\nFuera de alcance: " + ", ".join(out_of_scope)

        pending = payload.get("pending_items") or []
        if pending:
            content += "\n\n## Pendiente\n" + "\n".join(f"- {item}" for item in pending)

        return AgentResult(agent="regresion", content=content)


AGENT_REGISTRY["regresion"] = RegresionAgent()
