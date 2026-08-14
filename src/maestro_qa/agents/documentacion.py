import json

from ..json_extraction import extract_json
from ..orchestrator import AgentResult, Intake
from ..providers import Provider
from .registry import AGENT_REGISTRY

_VALID_DOC_TYPES = {"changelog", "user_guide", "technical_reference", "test_plan_summary"}

_SYSTEM_PROMPT = """Sos un agente de QA que redacta documentación a partir de un ticket o \
feature — el tipo de documento que un QA termina escribiendo después de entender una \
feature lo suficiente para probarla.

Elegí UN tipo de documento, el más adecuado al ticket (no generes los 4 siempre):
- changelog: entrada breve de qué cambió, para release notes.
- user_guide: cómo usar la feature desde la perspectiva de un usuario final.
- technical_reference: comportamiento y contrato técnico, para otros devs/QA.
- test_plan_summary: qué se cubrió y qué no, a partir de los casos de prueba.

Si el mensaje incluye una sección "Casos de prueba ya generados", redactá el \
comportamiento y los edge cases desde esos casos reales (`title`, `objective`, \
`expected_result`) — no reinventes el análisis del ticket desde cero.

Devolvé EXCLUSIVAMENTE un objeto JSON (sin texto adicional, sin markdown) con estos campos:
{
  "doc_type": "changelog|user_guide|technical_reference|test_plan_summary",
  "title": "...",
  "summary": "...",
  "sections": [{"heading": "...", "content": "..."}],
  "pending_items": ["información faltante para completar la doc, puede estar vacía"]
}
"""


def _validate(payload: dict[str, object]) -> None:
    if payload.get("doc_type") not in _VALID_DOC_TYPES:
        raise ValueError(f"doc_type inválido: {payload.get('doc_type')!r}, debe ser uno de {sorted(_VALID_DOC_TYPES)}")
    if not payload.get("title") or not payload.get("summary"):
        raise ValueError("El documento debe tener title y summary no vacíos")
    sections = payload.get("sections")
    if not isinstance(sections, list) or not sections:
        raise ValueError("El documento debe tener al menos una sección")
    for index, section in enumerate(sections):
        if not section.get("heading") or not section.get("content"):
            raise ValueError(f"Sección {index + 1}: heading y content no pueden estar vacíos")


class DocumentacionAgent:
    def run(self, intake: Intake, provider: Provider) -> AgentResult:
        raw = provider.complete(system=_SYSTEM_PROMPT, messages=[{"role": "user", "content": intake.text}])
        payload = json.loads(extract_json(raw, dict))
        _validate(payload)

        sections_text = "\n\n".join(f"### {s['heading']}\n{s['content']}" for s in payload["sections"])
        content = f"# [{payload['doc_type']}] {payload['title']}\n\n{payload['summary']}\n\n{sections_text}"

        pending = payload.get("pending_items") or []
        if pending:
            content += "\n\n## Pendiente\n" + "\n".join(f"- {item}" for item in pending)

        return AgentResult(agent="documentacion", content=content)


AGENT_REGISTRY["documentacion"] = DocumentacionAgent()
