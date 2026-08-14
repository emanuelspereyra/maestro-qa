from pathlib import Path
from typing import Literal

from mcp.server import MCPServer

from . import config, onboarding, readers, version_check

# Registra los 10 agentes en AGENT_REGISTRY (efecto de solo importar cada módulo).
# orchestrator.py no los importa él mismo a propósito (evita import circular, ver
# specs/002 y 008) — este es el punto de entrada real que sí necesita registrarlos.
from .agents import (  # noqa: F401
    automatizacion,
    automatizacion_api,
    bug_explorer,
    calidad_codigo,
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


def _run_qa_from_work_item_impl(work_item_id: str) -> str:
    config.load_env_file()
    try:
        reader = readers.get_reader()
    except ValueError as exc:
        return f"No se pudo configurar el reader ({exc})"
    if reader is None:
        return "No hay reader configurado (falta MAESTRO_READER=azure_devops y sus credenciales)."

    try:
        ticket = reader.fetch(work_item_id)
    except readers.ReaderError as exc:
        return f"No se pudo leer el work item {work_item_id} de Azure DevOps: {exc}"

    return _run_qa_impl("jira_ticket", ticket.text)


def _ensure_project_impl() -> str:
    config.load_env_file()
    status = onboarding.ensure_project()

    repos = "\n".join(f"- {name}: {info}" for name, info in status.repos.items()) or "Ninguno configurado."
    env_vars = "\n".join(
        f"- {name}: {'configurada' if configured else 'falta'}" for name, configured in status.env.items()
    )
    result = f"qa-project.yaml: {status.qa_project_path}\n\nRepos:\n{repos}\n\nVariables:\n{env_vars}"

    update_notice = version_check.check_for_update()
    if update_notice:
        result += f"\n\n{update_notice}"
    return result


@mcp.tool()
def run_qa(source: Literal["jira_ticket", "spec"], text: str) -> str:
    """Corre Maestro QA sobre un ticket de Jira o una spec/PRD.

    Rutea automáticamente a los agentes especializados que apliquen (casos manuales,
    automatización, datos de prueba, performance, seguridad, etc.) y devuelve el reporte
    agregado, incluyendo el veredicto final de release-readiness.
    """
    return _run_qa_impl(source, text)


@mcp.tool()
def run_qa_from_work_item(work_item_id: str) -> str:
    """Trae un work item real de Azure DevOps por ID y corre Maestro QA sobre su
    contenido — sin copiar/pegar texto a mano. Necesita MAESTRO_READER=azure_devops
    configurado (mismas credenciales que el writer de spec 027).
    """
    return _run_qa_from_work_item_impl(work_item_id)


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
