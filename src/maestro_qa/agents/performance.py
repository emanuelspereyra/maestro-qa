import ast
import json
import re

from ..orchestrator import AgentResult, Intake
from ..providers import Provider
from .registry import AGENT_REGISTRY

_SYSTEM_PROMPT = """Sos un agente de QA que genera pruebas de performance en Locust \
(Python) a partir de un ticket o feature. Maestro QA es Python de punta a punta — nunca \
generás Artillery (Node.js) salvo que el mensaje lo pida explícitamente.

Reglas obligatorias:
- NO inventes umbrales, usuarios concurrentes, duración ni SLA que no estén en el ticket. \
Si falta el objetivo del ensayo, tráfico esperado, usuarios concurrentes, duración, \
SLA/percentiles, error rate permitido, ventana de ejecución o responsable, agregalo a \
`pending_items` en vez de inventarlo.
- Clasificá el ensayo en uno de: baseline, load, stress, spike, endurance, volume.
- El host NUNCA se hardcodea — se resuelve vía el perfil `QA_TARGET_ENV`/
  `QA_<AMBIENTE>_API_BASE_URL` (mismo patrón que el resto del proyecto), nunca una URL fija \
de un ambiente.
- Si el mensaje incluye una sección "Casos de prueba ya generados", derivá los flujos \
críticos a probar de esos casos (no traduzcas cada caso funcional a carga — elegí los \
recorridos representativos del uso real).

Devolvé EXCLUSIVAMENTE un objeto JSON (sin texto adicional, sin markdown) con estos campos:
{
  "test_type": "baseline|load|stress|spike|endurance|volume",
  "locustfile_filename": "performance/locustfile_<feature>.py",
  "locustfile_code": "<código Python completo del locustfile>",
  "run_command": "<comando locust reproducible, ej. locust -f <archivo> --headless -u 50 -r 5 -t 5m>",
  "pending_items": ["<NFRs faltantes o supuestos, puede estar vacía>"]
}
"""


def _extract_json_object(text: str) -> str:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("La respuesta del LLM no contiene un objeto JSON")
    return match.group(0)


class PerformanceAgent:
    def run(self, intake: Intake, provider: Provider) -> AgentResult:
        raw = provider.complete(system=_SYSTEM_PROMPT, messages=[{"role": "user", "content": intake.text}])
        payload = json.loads(_extract_json_object(raw))

        try:
            ast.parse(payload["locustfile_code"])
        except SyntaxError as exc:
            raise ValueError(f"{payload['locustfile_filename']}: código Python inválido ({exc})") from exc

        sections = [
            f"Tipo de ensayo: {payload['test_type']}",
            f"## {payload['locustfile_filename']}\n```python\n{payload['locustfile_code']}\n```",
            f"Comando: `{payload['run_command']}`",
        ]
        pending = payload.get("pending_items") or []
        if pending:
            sections.append("## Pendiente\n" + "\n".join(f"- {item}" for item in pending))

        return AgentResult(agent="performance", content="\n\n".join(sections))


AGENT_REGISTRY["performance"] = PerformanceAgent()
