from pathlib import Path
from typing import Literal

from mcp.server import MCPServer

from . import config, onboarding

# Registra los 10 agentes en AGENT_REGISTRY (efecto de solo importar cada módulo).
# orchestrator.py no los importa él mismo a propósito (evita import circular, ver
# specs/002 y 008) — este es el punto de entrada real que sí necesita registrarlos.
from .agents import (  # noqa: F401
    automatizacion,
    automatizacion_api,
    casos_manuales,
    datos_prueba,
    documentacion,
    performance,
    priorizacion_bugs,
    regresion,
    release_readiness,
    seguridad,
    trazabilidad,
)
from .orchestrator import Intake, run
from .providers import get_provider

mcp = MCPServer("maestro-qa")


def _run_qa_impl(source: str, text: str) -> str:
    config.load_env_file()
    provider = get_provider()
    intake = Intake(source=source, text=text)  # type: ignore[arg-type]
    result = run(intake, provider, history_dir=Path("qa-history"))
    return result.to_markdown()


def _ensure_project_impl() -> str:
    config.load_env_file()
    status = onboarding.ensure_project()

    repos = "\n".join(f"- {name}: {info}" for name, info in status.repos.items()) or "Ninguno configurado."
    env_vars = "\n".join(
        f"- {name}: {'configurada' if configured else 'falta'}" for name, configured in status.env.items()
    )
    return f"qa-project.yaml: {status.qa_project_path}\n\nRepos:\n{repos}\n\nVariables:\n{env_vars}"


@mcp.tool()
def run_qa(source: Literal["jira_ticket", "spec"], text: str) -> str:
    """Corre Maestro QA sobre un ticket de Jira o una spec/PRD.

    Rutea automáticamente a los agentes especializados que apliquen (casos manuales,
    automatización, datos de prueba, performance, seguridad, etc.) y devuelve el reporte
    agregado, incluyendo el veredicto final de release-readiness.
    """
    return _run_qa_impl(source, text)


@mcp.tool()
def ensure_project() -> str:
    """Crea o verifica qa-project.yaml y reporta qué credenciales propias de Maestro QA
    (no las del proyecto del cliente bajo prueba) están configuradas, sin exponer valores.
    """
    return _ensure_project_impl()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
