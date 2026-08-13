import os
import re
from pathlib import Path

_ASSIGNMENT = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")

# Catálogo de variables propias de Maestro QA — ver .env.example. No incluye las
# QA_<AMBIENTE>_* del proyecto del cliente bajo prueba (spec 009).
KNOWN_VARIABLES = [
    "MAESTRO_PROVIDER",
    "MAESTRO_MODEL",
    "MAESTRO_API_KEY",
    "MAESTRO_GITHUB_TOKEN",
    "MAESTRO_JIRA_URL",
    "MAESTRO_JIRA_EMAIL",
    "MAESTRO_JIRA_TOKEN",
    "MAESTRO_TRELLO_KEY",
    "MAESTRO_TRELLO_TOKEN",
]


def load_env_file(path: Path | None = None) -> None:
    """Carga asignaciones de .env al proceso sin pisar variables ya seteadas ni loguear valores."""
    selected = path or Path(os.environ.get("MAESTRO_ENV_FILE", ".env"))
    if not selected.is_file():
        return
    for line in selected.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = _ASSIGNMENT.match(line)
        if not match:
            continue
        name, value = match.groups()
        if name not in os.environ:
            os.environ[name] = value.strip().strip("'\"")


def env_status(names: list[str] | None = None) -> dict[str, bool]:
    """Configurado/no-configurado por nombre de variable — nunca expone el valor."""
    return {name: bool(os.environ.get(name)) for name in (names or KNOWN_VARIABLES)}
