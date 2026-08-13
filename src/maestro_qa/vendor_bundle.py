import os
from pathlib import Path

# ponytail: ruta relativa al repo — rompe si el paquete se instala fuera de este
# repo. Ver specs/004-agente-casos-manuales.md backlog.
_DEFAULT_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[2]
    / "vendor"
    / "qa-intelligent-skill-bundle"
    / "skills"
    / "generate-qa-from-test-cases"
    / "scripts"
)


def scripts_dir() -> Path:
    return Path(os.environ.get("MAESTRO_QA_BUNDLE_SCRIPTS", str(_DEFAULT_SCRIPTS_DIR)))
