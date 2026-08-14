import ast
import json

from ..json_extraction import extract_json
from ..orchestrator import AgentResult, Intake
from ..providers import Provider
from .registry import AGENT_REGISTRY

_SYSTEM_PROMPT = """Sos un agente de QA que genera automatización de API backend con \
pytest + HTTPX, a partir de la descripción de un ticket o feature. Maestro QA es Python de \
punta a punta — nunca generás REST Assured (Java) salvo que el mensaje lo pida \
explícitamente.

Reglas obligatorias:
- El cliente de API usa HTTPX, recibe la URL base vía la fixture `api_base_url` (ya existe \
en el proyecto vía conftest.py) — nunca hardcodear la URL ni el ambiente.
- El test valida status, schema/campos relevantes, headers importantes, manejo de errores, \
autorización, e idempotencia o persistencia cuando aplique.
- NUNCA loguear ni imprimir el header Authorization, cookies ni cuerpos con datos sensibles.
- Si falta un endpoint, contrato o dato para escribir el código real, NO lo inventes: \
agregalo a `pending_items` y dejá ese punto con un comentario `# TODO:` claro.
- Si el mensaje incluye una sección "Casos de prueba ya generados", el test tiene que \
automatizar EXACTAMENTE los `steps` de los casos con layer "backend" y execution_type \
"automated" o "both" — no un flujo distinto inventado del ticket.

Devolvé EXCLUSIVAMENTE un objeto JSON (sin texto adicional, sin markdown) con estos campos:
{
  "api_client_filename": "clients/<feature>_client.py",
  "api_client_code": "<código Python completo del cliente HTTPX>",
  "test_filename": "tests/test_<feature>_api.py",
  "test_code": "<código Python completo del test>",
  "pending_items": ["<lista de puntos pendientes, puede estar vacía>"]
}
"""


_REQUIRED_FIELDS = ["api_client_filename", "api_client_code", "test_filename", "test_code"]


def _check_syntax(filename: str, code: str) -> None:
    try:
        ast.parse(code)
    except SyntaxError as exc:
        raise ValueError(f"{filename}: código Python inválido ({exc})") from exc


def _validate(payload: dict[str, object]) -> None:
    missing = [field for field in _REQUIRED_FIELDS if not payload.get(field)]
    if missing:
        raise ValueError(f"Respuesta incompleta del agente de automatización de API, faltan campos: {', '.join(missing)}")


class AutomatizacionApiAgent:
    def run(self, intake: Intake, provider: Provider) -> AgentResult:
        raw = provider.complete(system=_SYSTEM_PROMPT, messages=[{"role": "user", "content": intake.text}])
        payload = json.loads(extract_json(raw, dict))
        _validate(payload)

        _check_syntax(payload["api_client_filename"], payload["api_client_code"])
        _check_syntax(payload["test_filename"], payload["test_code"])

        sections = [
            f"## {payload['api_client_filename']}\n```python\n{payload['api_client_code']}\n```",
            f"## {payload['test_filename']}\n```python\n{payload['test_code']}\n```",
        ]
        pending = payload.get("pending_items") or []
        if pending:
            sections.append("## Pendiente\n" + "\n".join(f"- {item}" for item in pending))

        return AgentResult(agent="automatizacion_api", content="\n\n".join(sections))


AGENT_REGISTRY["automatizacion_api"] = AutomatizacionApiAgent()
