import json

from ..json_extraction import extract_json
from ..orchestrator import AgentResult, Intake
from ..providers import Provider
from .registry import AGENT_REGISTRY

_VALID_SEVERITIES = {"Critical", "High", "Medium", "Low"}
_VALID_REPRODUCIBILITY = {"siempre", "intermitente", "no_reproducido"}
_REQUIRED_FIELDS = [
    "title",
    "case_id_o_fuente",
    "ambiente_y_versiones",
    "preconditions",
    "datos_usados",
    "steps",
    "expected_result",
    "actual_result",
    "reproducibility",
    "severity",
    "business_priority",
    "evidence_required",
]

_SYSTEM_PROMPT = """Sos un agente de QA que redacta un BORRADOR de defecto a partir de un \
ticket o de un caso de prueba que falló — nunca lo publicás, nunca buscás duplicados reales \
(no tenés acceso de lectura a ningún tracker todavía).

Separá severidad técnica de prioridad de negocio: vos sugerís la severidad (impacto \
técnico), la prioridad de negocio queda como "pendiente de decisión de negocio" — no la \
decidís vos.

Severidades válidas: Critical (pérdida grave, seguridad o indisponibilidad crítica), High \
(flujo principal bloqueado sin workaround), Medium (degradación con workaround), Low \
(impacto menor o cosmético).

Si el mensaje incluye una sección "Casos de prueba ya generados" y alguno describe un fallo \
relevante, usá ESE caso como fuente (`case_id_o_fuente`) en vez de inventar un escenario \
nuevo.

Devolvé EXCLUSIVAMENTE un objeto JSON (sin texto adicional, sin markdown) con estos campos:
{
  "title": "...",
  "case_id_o_fuente": "...",
  "ambiente_y_versiones": "...",
  "preconditions": ["..."],
  "datos_usados": "...",
  "steps": ["..."],
  "expected_result": "...",
  "actual_result": "...",
  "reproducibility": "siempre|intermitente|no_reproducido",
  "severity": "Critical|High|Medium|Low",
  "business_priority": "pendiente de decisión de negocio",
  "evidence_required": ["..."]
}
"""


def _validate(payload: dict[str, object]) -> None:
    missing = [field for field in _REQUIRED_FIELDS if not payload.get(field)]
    if missing:
        raise ValueError(f"Borrador de defecto incompleto, faltan campos: {', '.join(missing)}")
    if payload["severity"] not in _VALID_SEVERITIES:
        raise ValueError(f"severity inválida: {payload['severity']!r}, debe ser una de {sorted(_VALID_SEVERITIES)}")
    if payload["reproducibility"] not in _VALID_REPRODUCIBILITY:
        raise ValueError(
            f"reproducibility inválida: {payload['reproducibility']!r}, "
            f"debe ser una de {sorted(_VALID_REPRODUCIBILITY)}"
        )


class PriorizacionBugsAgent:
    def run(self, intake: Intake, provider: Provider) -> AgentResult:
        raw = provider.complete(system=_SYSTEM_PROMPT, messages=[{"role": "user", "content": intake.text}])
        payload = json.loads(extract_json(raw, dict))
        _validate(payload)

        content = (
            "**Borrador sin duplicados verificados ni publicación real** "
            "(no hay lectura de tracker ni writer conectado todavía)\n\n"
            f"## {payload['title']}\n"
            f"Fuente: {payload['case_id_o_fuente']}\n"
            f"Ambiente/versiones: {payload['ambiente_y_versiones']}\n"
            f"Severidad sugerida: {payload['severity']} — "
            f"Prioridad de negocio: {payload['business_priority']}\n"
            f"Reproducibilidad: {payload['reproducibility']}\n\n"
            f"Precondiciones: {', '.join(payload['preconditions'])}\n"
            f"Datos usados: {payload['datos_usados']}\n"
            f"Pasos: {', '.join(payload['steps'])}\n"
            f"Resultado esperado: {payload['expected_result']}\n"
            f"Resultado obtenido: {payload['actual_result']}\n"
            f"Evidencia requerida: {', '.join(payload['evidence_required'])}"
        )
        return AgentResult(agent="priorizacion_bugs", content=content)


AGENT_REGISTRY["priorizacion_bugs"] = PriorizacionBugsAgent()
