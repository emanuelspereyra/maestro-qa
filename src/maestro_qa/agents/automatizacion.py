import ast
import json

from ..json_extraction import extract_json
from ..orchestrator import AgentResult, Intake
from ..providers import Provider
from .registry import AGENT_REGISTRY

_SYSTEM_PROMPT = """Sos un agente de QA que genera automatización frontend en Playwright \
Python con Page Object Model, a partir de la descripción de un ticket o feature.

Reglas obligatorias:
- El Page Object es una subclase de `BasePage` (importada como \
`from pages.base_page import BasePage`), que ya expone `self.page` y `self.base_url`.
- El test usa pytest y las fixtures `base_url` y `qa_target_environment` (ya existen en el \
proyecto vía conftest.py) — nunca hardcodear URLs ni ambientes.
- Locators por rol, label, placeholder o test id. Nunca XPath/CSS frágil sin justificar.
- Web-first assertions de Playwright (`expect(locator).to_be_visible()`, etc.), nunca \
`time.sleep`.
- Si falta una URL, selector, dato o contrato para escribir el código real, NO lo inventes: \
agregalo a `pending_items` y dejá ese punto del código con un comentario `# TODO:` claro.
- Si el mensaje incluye una sección "Casos de prueba ya generados", el test que escribas \
tiene que automatizar EXACTAMENTE los `steps` de los casos con layer "frontend" y \
execution_type "automated" o "both" — no un flujo distinto inventado del ticket.

Devolvé EXCLUSIVAMENTE un objeto JSON (sin texto adicional, sin markdown) con estos campos:
{
  "page_object_filename": "pages/<feature>_page.py",
  "page_object_code": "<código Python completo del Page Object>",
  "test_filename": "tests/test_<feature>.py",
  "test_code": "<código Python completo del test>",
  "pending_items": ["<lista de puntos pendientes, puede estar vacía>"]
}
"""


_REQUIRED_FIELDS = ["page_object_filename", "page_object_code", "test_filename", "test_code"]


def _check_syntax(filename: str, code: str) -> None:
    try:
        ast.parse(code)
    except SyntaxError as exc:
        raise ValueError(f"{filename}: código Python inválido ({exc})") from exc


def _validate(payload: dict[str, object]) -> None:
    missing = [field for field in _REQUIRED_FIELDS if not payload.get(field)]
    if missing:
        raise ValueError(f"Respuesta incompleta del agente de automatización, faltan campos: {', '.join(missing)}")


class AutomatizacionAgent:
    def run(self, intake: Intake, provider: Provider) -> AgentResult:
        raw = provider.complete(system=_SYSTEM_PROMPT, messages=[{"role": "user", "content": intake.text}])
        payload = json.loads(extract_json(raw, dict))
        _validate(payload)

        _check_syntax(payload["page_object_filename"], payload["page_object_code"])
        _check_syntax(payload["test_filename"], payload["test_code"])

        sections = [
            f"## {payload['page_object_filename']}\n```python\n{payload['page_object_code']}\n```",
            f"## {payload['test_filename']}\n```python\n{payload['test_code']}\n```",
        ]
        pending = payload.get("pending_items") or []
        if pending:
            sections.append("## Pendiente\n" + "\n".join(f"- {item}" for item in pending))

        return AgentResult(agent="automatizacion", content="\n\n".join(sections))


AGENT_REGISTRY["automatizacion"] = AutomatizacionAgent()
