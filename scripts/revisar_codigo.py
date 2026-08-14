"""Corre calidad_codigo standalone sobre un archivo o diff, sin pasar por el orquestador/
clasificación de tickets (spec 025). No corre en CI (necesita una API key real). Uso:

    MAESTRO_PROVIDER=anthropic MAESTRO_MODEL=claude-sonnet-5 MAESTRO_API_KEY=sk-... \
        .venv/bin/python scripts/revisar_codigo.py ruta/al/archivo_o_diff
"""

import sys
from pathlib import Path

from maestro_qa.agents.calidad_codigo import CalidadCodigoAgent
from maestro_qa.orchestrator import Intake
from maestro_qa.providers import get_provider


def main() -> None:
    if len(sys.argv) != 2:
        print("Uso: revisar_codigo.py <archivo_o_diff>", file=sys.stderr)
        raise SystemExit(2)

    path = Path(sys.argv[1])
    content = path.read_text(encoding="utf-8")
    intake = Intake(source="spec", text=f"Revisar este código ({path.name}):\n\n```\n{content}\n```")

    result = CalidadCodigoAgent().run(intake, get_provider())
    print(result.content)


if __name__ == "__main__":
    main()
