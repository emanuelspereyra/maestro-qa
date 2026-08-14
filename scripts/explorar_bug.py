"""Corre bug_explorer standalone sobre la descripción de un bug, sin pasar por el
orquestador/clasificación de tickets (spec 029). No corre en CI (necesita una API key
real). Uso:

    MAESTRO_PROVIDER=anthropic MAESTRO_MODEL=claude-sonnet-5 MAESTRO_API_KEY=sk-... \
        .venv/bin/python scripts/explorar_bug.py ruta/al/archivo_con_la_descripcion
"""

import sys
from pathlib import Path

from maestro_qa.agents.bug_explorer import BugExplorerAgent
from maestro_qa.orchestrator import Intake
from maestro_qa.providers import get_provider


def main() -> None:
    if len(sys.argv) != 2:
        print("Uso: explorar_bug.py <archivo_con_la_descripcion_del_bug>", file=sys.stderr)
        raise SystemExit(2)

    path = Path(sys.argv[1])
    description = path.read_text(encoding="utf-8")
    intake = Intake(source="spec", text=description)

    result = BugExplorerAgent().run(intake, get_provider())
    print(result.content)


if __name__ == "__main__":
    main()
