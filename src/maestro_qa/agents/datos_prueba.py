import json
import subprocess
import tempfile
from pathlib import Path

from .. import vendor_bundle
from ..json_extraction import extract_json
from ..orchestrator import AgentResult, Intake
from ..providers import Provider
from .registry import AGENT_REGISTRY

_SYSTEM_PROMPT = """Sos un agente de QA que describe la FORMA de un dataset de prueba a \
partir de un ticket o feature — no generás los valores, eso lo hace un generador \
determinista aparte.

Si el mensaje incluye una sección "Casos de prueba ya generados" con casos que tienen \
"data_contract" (dataset_id, requirements), tu dataset-spec DEBE cubrir esos requirements \
reales — usá el mismo dataset_id que aparece ahí en vez de inventar uno nuevo, y una \
entidad/campo por cada requirement listado. Si no hay esa sección, describí el dataset a \
partir del ticket como siempre.

Devolvé EXCLUSIVAMENTE un objeto JSON (sin texto adicional, sin markdown) con este \
contrato:
{
  "dataset_id": "DS-<feature>-001",
  "seed": 12345,
  "entities": [
    {
      "name": "<nombre de la entidad>",
      "target": "<tabla o destino, ej. dbo.users>",
      "identifier_fields": ["id"],
      "display_fields": ["<campos visibles no sensibles>"],
      "sensitive_fields": [],
      "count": 2,
      "fields": {
        "<nombre_campo>": {"type": "<tipo>", "...": "..."}
      }
    }
  ]
}

Tipos de campo soportados (usar EXACTAMENTE estos nombres y parámetros):
- literal: {"type": "literal", "value": <cualquier valor fijo>}
- run_id: {"type": "run_id"}
- uuid: {"type": "uuid"}
- integer: {"type": "integer", "min": <int>, "max": <int>}
- decimal: {"type": "decimal", "min": <num>, "max": <num>, "scale": <int>}
- boolean: {"type": "boolean"}
- choice: {"type": "choice", "values": [<opciones>]}
- string: {"type": "string", "prefix": "<str>", "length": <int>}
- username: {"type": "username", "prefix": "<str>"}
- email: {"type": "email", "domain": "<str>"}
- date / datetime: {"type": "date", "base": "<ISO8601>"}
- ref: {"type": "ref", "entity": "<otra entidad>", "field": "<campo>"}

No inventes campos sensibles reales (passwords, tokens) — si la feature los necesita, \
listalos en sensitive_fields con un tipo sintético (ej. string), nunca literal con un valor \
que parezca un secreto real.
"""


class DatosPruebaAgent:
    def run(self, intake: Intake, provider: Provider) -> AgentResult:
        raw = provider.complete(system=_SYSTEM_PROMPT, messages=[{"role": "user", "content": intake.text}])
        spec = json.loads(extract_json(raw, dict))
        dataset_id = spec.get("dataset_id", "DS-UNKNOWN")

        scripts_dir = vendor_bundle.scripts_dir()
        output_dir = Path.cwd() / "qa-artifacts" / "data" / dataset_id
        output_dir.mkdir(parents=True, exist_ok=True)
        dataset_path = output_dir / "dataset.json"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as spec_file:
            json.dump(spec, spec_file, ensure_ascii=False)
            spec_path = Path(spec_file.name)

        try:
            generation = subprocess.run(
                [
                    "python3",
                    str(scripts_dir / "generate_dataset.py"),
                    str(spec_path),
                    "--output",
                    str(dataset_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        finally:
            spec_path.unlink(missing_ok=True)

        if generation.returncode != 0:
            raise ValueError(f"generate_dataset.py falló: {generation.stdout.strip()}")

        summary = json.loads(generation.stdout)
        rows_by_entity = "\n".join(
            f"- {target['entity']} ({target['target']}): {target['rows']} filas"
            for target in summary["targets"]
        )
        content = (
            f"Dataset {summary['dataset_id']} — estado {summary['status']}, "
            f"{summary['rows']} filas en {summary['entities']} entidades\n\n"
            f"{rows_by_entity}\n\n"
            f"Artefactos: {summary['output']}, {summary['csv_dir']}, "
            f"{summary['inventory_markdown']}"
        )
        return AgentResult(agent="datos_prueba", content=content)


AGENT_REGISTRY["datos_prueba"] = DatosPruebaAgent()
