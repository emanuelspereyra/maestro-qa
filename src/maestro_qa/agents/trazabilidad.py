import json

from ..json_extraction import extract_json
from ..orchestrator import AgentResult, Intake
from ..providers import Provider
from .registry import AGENT_REGISTRY

_VALID_STATUSES = {"covered", "gap"}

_SYSTEM_PROMPT = """Sos un agente de QA que cruza los criterios de aceptación de un ticket \
contra los casos de prueba que ya se generaron en el mismo run — para decir explícito qué \
quedó cubierto y qué no. No generás casos nuevos (eso es trabajo de otro agente).

Extraé los criterios de aceptación del ticket. Si el ticket no los lista explícitos, \
derivá al menos uno de la descripción y marcalo en `pending_items` como derivado (no \
devuelvas una lista vacía en silencio).

Si el mensaje incluye una sección "Casos de prueba ya generados", cruzá cada criterio: si \
algún caso lo cubre (por su `business_rule_ids` o el contenido de su `objective`), \
marcalo `covered` con los `case_ids` reales que lo cubren. Si ningún caso lo cubre, \
marcalo `gap` — no inventes cobertura que no existe. Si NO hay casos generados en el \
mensaje, todos los criterios quedan `gap`.

Los casos generados que no tengan `business_rule_ids` van a `untraceable_cases` — un caso \
que no se puede justificar contra ningún requisito es una señal real, no se oculta.

Devolvé EXCLUSIVAMENTE un objeto JSON (sin texto adicional, sin markdown) con estos campos:
{
  "acceptance_criteria": [{"id": "AC-1", "text": "..."}],
  "traceability_matrix": [
    {"criterion_id": "AC-1", "case_ids": ["..."], "status": "covered|gap"}
  ],
  "untraceable_cases": ["case_ids sin business_rule_ids, puede estar vacía"],
  "pending_items": ["puede estar vacía"]
}
"""


def _validate(payload: dict[str, object]) -> None:
    criteria = payload.get("acceptance_criteria")
    if not criteria:
        raise ValueError("acceptance_criteria no puede estar vacío")
    if not isinstance(criteria, list):
        raise ValueError("acceptance_criteria debe ser una lista")  # noqa: TRY004 - convención del proyecto: ValueError para toda validación de input
    for index, criterion in enumerate(criteria):
        if not criterion.get("id") or not criterion.get("text"):
            raise ValueError(f"acceptance_criteria[{index}]: faltan campos 'id'/'text'")
    matrix = payload.get("traceability_matrix")
    if not isinstance(matrix, list) or not matrix:
        raise ValueError("traceability_matrix no puede estar vacía")
    for index, entry in enumerate(matrix):
        if not entry.get("criterion_id"):
            raise ValueError(f"traceability_matrix[{index}]: criterion_id no puede estar vacío")
        if entry.get("status") not in _VALID_STATUSES:
            raise ValueError(
                f"traceability_matrix[{index}]: status inválido {entry.get('status')!r}, "
                f"debe ser uno de {sorted(_VALID_STATUSES)}"
            )


class TrazabilidadAgent:
    def run(self, intake: Intake, provider: Provider) -> AgentResult:
        raw = provider.complete(system=_SYSTEM_PROMPT, messages=[{"role": "user", "content": intake.text}])
        payload = json.loads(extract_json(raw, dict))
        _validate(payload)

        criteria_by_id = {c["id"]: c["text"] for c in payload["acceptance_criteria"]}
        matrix_lines = []
        for entry in payload["traceability_matrix"]:
            text = criteria_by_id.get(entry["criterion_id"], entry["criterion_id"])
            cases = ", ".join(entry.get("case_ids") or []) or "(ninguno)"
            matrix_lines.append(f"- [{entry['status']}] {entry['criterion_id']} — {text} — casos: {cases}")

        gaps = sum(1 for e in payload["traceability_matrix"] if e["status"] == "gap")
        content = (
            f"Trazabilidad: {len(payload['traceability_matrix']) - gaps} cubiertos, {gaps} huecos\n\n"
            + "\n".join(matrix_lines)
        )

        untraceable = payload.get("untraceable_cases") or []
        if untraceable:
            content += "\n\nCasos sin ningún requisito asociado (no trazables): " + ", ".join(untraceable)

        pending = payload.get("pending_items") or []
        if pending:
            content += "\n\n## Pendiente\n" + "\n".join(f"- {item}" for item in pending)

        return AgentResult(agent="trazabilidad", content=content)


AGENT_REGISTRY["trazabilidad"] = TrazabilidadAgent()
