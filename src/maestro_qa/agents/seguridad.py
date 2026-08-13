import json
import re

from ..orchestrator import AgentResult, Intake
from ..providers import Provider
from .registry import AGENT_REGISTRY

_VALID_CATEGORIES = {
    "broken-access-control",
    "broken-authentication",
    "injection",
    "sensitive-data-exposure",
    "security-misconfiguration",
    "rate-limiting-and-dos",
    "ssrf",
}
_VALID_SEVERITIES = {"Critical", "High", "Medium", "Low"}
_REQUIRED_CASE_FIELDS = ["category", "title", "objective", "steps", "expected_result", "severity_if_fails"]

_SYSTEM_PROMPT = """Sos un agente de QA que genera CASOS de prueba de seguridad (no código \
ejecutable, no exploits reales) a partir de un ticket o feature, para que un humano los \
revise y eventualmente los automatice.

Categorías válidas — usá SOLO las que apliquen a la feature descrita, no fuerces las 7 \
siempre: broken-access-control, broken-authentication, injection, sensitive-data-exposure, \
security-misconfiguration, rate-limiting-and-dos, ssrf.

Para cada caso: pasos revisables por un humano (podés incluir una señal de prueba estándar \
y conocida, ej. `' OR '1'='1` para injection — nunca un exploit real ni código que se \
ejecute solo), y el `expected_result` describe el comportamiento SEGURO esperado (ej. "la \
API responde 403 sin exponer el registro de otro usuario").

Si el mensaje incluye una sección "Casos de prueba ya generados", usalos para decidir qué \
categorías aplican de verdad (ej. si hay un caso de login, aplican broken-authentication y \
broken-access-control; si una feature acepta una URL, aplica ssrf) — no inventes features \
que no estén ahí ni en el ticket.

Si una categoría aplicaría pero falta información del ticket para escribir el caso en \
concreto, agregala a `pending_items` en vez de inventar detalles.

Devolvé EXCLUSIVAMENTE un objeto JSON (sin texto adicional, sin markdown) con estos campos:
{
  "cases": [
    {
      "category": "<una de las categorías válidas>",
      "title": "...",
      "objective": "...",
      "steps": ["..."],
      "expected_result": "...",
      "severity_if_fails": "Critical|High|Medium|Low"
    }
  ],
  "pending_items": ["<puede estar vacía>"]
}
"""


def _extract_json_object(text: str) -> str:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("La respuesta del LLM no contiene un objeto JSON")
    return match.group(0)


def _validate(payload: dict[str, object]) -> None:
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("El payload debe incluir al menos un caso de seguridad")
    for index, case in enumerate(cases):
        label = f"caso {index + 1}"
        missing = [field for field in _REQUIRED_CASE_FIELDS if not case.get(field)]
        if missing:
            raise ValueError(f"{label}: faltan campos {', '.join(missing)}")
        if case["category"] not in _VALID_CATEGORIES:
            raise ValueError(f"{label}: category inválida {case['category']!r}, debe ser una de {sorted(_VALID_CATEGORIES)}")
        if case["severity_if_fails"] not in _VALID_SEVERITIES:
            raise ValueError(
                f"{label}: severity_if_fails inválida {case['severity_if_fails']!r}, "
                f"debe ser una de {sorted(_VALID_SEVERITIES)}"
            )


class SeguridadAgent:
    def run(self, intake: Intake, provider: Provider) -> AgentResult:
        raw = provider.complete(system=_SYSTEM_PROMPT, messages=[{"role": "user", "content": intake.text}])
        payload = json.loads(_extract_json_object(raw))
        _validate(payload)

        sections = []
        for case in payload["cases"]:
            steps = "\n".join(f"  {i + 1}. {step}" for i, step in enumerate(case["steps"]))
            sections.append(
                f"## [{case['category']}] {case['title']}\n"
                f"Objetivo: {case['objective']}\n"
                f"Pasos:\n{steps}\n"
                f"Resultado esperado (comportamiento seguro): {case['expected_result']}\n"
                f"Severidad si falla: {case['severity_if_fails']}"
            )

        pending = payload.get("pending_items") or []
        if pending:
            sections.append("## Pendiente\n" + "\n".join(f"- {item}" for item in pending))

        return AgentResult(agent="seguridad", content="\n\n".join(sections))


AGENT_REGISTRY["seguridad"] = SeguridadAgent()
