import os
from pathlib import Path

# El bundle vive DENTRO del paquete (src/maestro_qa/vendor/...) a propósito — spec 021:
# así queda incluido en cualquier instalación (editable, wheel, uvx, pipx), no solo en un
# checkout completo del repo. Ruta relativa al propio paquete, no al repo.
_DEFAULT_SCRIPTS_DIR = (
    Path(__file__).resolve().parent
    / "vendor"
    / "qa-intelligent-skill-bundle"
    / "skills"
    / "generate-qa-from-test-cases"
    / "scripts"
)


def scripts_dir() -> Path:
    return Path(os.environ.get("MAESTRO_QA_BUNDLE_SCRIPTS", str(_DEFAULT_SCRIPTS_DIR)))
