import json
import re
import subprocess
import tempfile
from pathlib import Path

from .. import vendor_bundle
from ..orchestrator import AgentResult, Intake
from ..providers import Provider
from .registry import AGENT_REGISTRY

_SYSTEM_PROMPT = """Sos un agente de QA que genera casos de prueba manuales en el \
contrato canónico de FÓRMULA de casos de prueba. Te llega la descripción de una feature o \
ticket. Devolvé EXCLUSIVAMENTE un array JSON de casos (sin texto adicional, sin markdown, \
sin envolver en un objeto con clave "cases") donde cada caso tiene EXACTAMENTE estos campos:

case_id, feature_id, layer (frontend|backend|e2e|data|performance), scenario_family \
(happy-path|alternate-path|unhappy-path|boundary|state-transition|authorization|\
data-integrity|contract|integration|resilience|concurrency|time|calculation|\
search-listing|accessibility|compatibility|performance|audit-observability), \
business_rule_ids (lista de strings), coverage_dimensions (lista de strings), title, \
objective, sources (lista de strings), work_item_ids (lista de strings), confidence \
(confirmed|inferred|pending), priority (critical|high|medium|low), execution_type \
(manual|automated|both), preconditions (lista de strings), steps (lista de objetos con \
order entero desde 1, action, expected), expected_result, actual_result (siempre \
"Pendiente"), status (siempre "NOT_EXECUTED"), data_contract (objeto con dataset_id, \
requirements, setup_method, cleanup_method — todos de setup_method/cleanup_method deben \
ser uno de: api|sql|nosql|ui|fixture|none), evidence_required (lista de strings).

Generá como mínimo happy-path, unhappy-path y boundary para cada capa aplicable a la \
feature descrita. Ejemplo de formato (una sola capa, adaptá al feature real):

[
  {
    "case_id": "FE-TC-001",
    "feature_id": "users.create",
    "layer": "frontend",
    "scenario_family": "happy-path",
    "business_rule_ids": ["BR-USERS-001"],
    "coverage_dimensions": ["authorized-role", "valid-data"],
    "title": "Crear usuario válido desde la interfaz",
    "objective": "Verificar el flujo visible de creación de un usuario autorizado",
    "sources": ["REQ-001"],
    "work_item_ids": [],
    "confidence": "confirmed",
    "priority": "high",
    "execution_type": "both",
    "preconditions": ["Ambiente QA disponible"],
    "steps": [
      {"order": 1, "action": "Abrir el formulario", "expected": "El formulario se muestra"}
    ],
    "expected_result": "El usuario queda creado y visible",
    "actual_result": "Pendiente",
    "status": "NOT_EXECUTED",
    "data_contract": {
      "dataset_id": "DS-USERS-001",
      "requirements": ["Usuario único"],
      "setup_method": "api",
      "cleanup_method": "api"
    },
    "evidence_required": ["screenshot"]
  }
]
"""


def _extract_json_array(text: str) -> str:
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        raise ValueError("La respuesta del LLM no contiene un array JSON de casos")
    return match.group(0)


class CasosManualesAgent:
    def run(self, intake: Intake, provider: Provider) -> AgentResult:
        raw = provider.complete(system=_SYSTEM_PROMPT, messages=[{"role": "user", "content": intake.text}])
        cases = json.loads(_extract_json_array(raw))
        scripts_dir = vendor_bundle.scripts_dir()

        layers_present = sorted({case.get("layer") for case in cases if case.get("layer")})
        document = {
            "coverage": {
                "required_layers": layers_present,
                "required_scenario_families": ["happy-path", "unhappy-path", "boundary"],
            },
            "cases": cases,
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            cases_path = Path(tmp_dir) / "cases.json"
            cases_path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")

            validation = subprocess.run(
                ["python3", str(scripts_dir / "validate_cases.py"), str(cases_path)],
                capture_output=True,
                text=True,
                check=False,
            )
            report = json.loads(validation.stdout)
            if report.get("errors"):
                raise ValueError(f"Casos inválidos: {'; '.join(report['errors'])}")

            rendered = subprocess.run(
                ["python3", str(scripts_dir / "render_manual_cases.py"), str(cases_path)],
                capture_output=True,
                text=True,
                check=True,
            ).stdout

        summary = (
            f"Cobertura: {report['delivery_status']} — {report['case_count']} casos, "
            f"capas {report['layer_counts']}"
        )
        return AgentResult(agent="casos_manuales", content=f"{summary}\n\n{rendered}")


AGENT_REGISTRY["casos_manuales"] = CasosManualesAgent()
