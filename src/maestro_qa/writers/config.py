import os

from .azure_devops import AzureDevOpsWriter
from .base import Writer

_AZURE_DEVOPS_REQUIRED_VARS = ("MAESTRO_AZURE_DEVOPS_ORG", "MAESTRO_AZURE_DEVOPS_PROJECT", "MAESTRO_AZURE_DEVOPS_PAT")


def get_writer() -> Writer | None:
    """None si MAESTRO_WRITER no está seteada — las integraciones de salida son
    opcionales, a diferencia del provider de LLM que es obligatorio."""
    name = os.environ.get("MAESTRO_WRITER", "").strip().lower()
    if not name:
        return None

    if name == "azure_devops":
        missing = [var for var in _AZURE_DEVOPS_REQUIRED_VARS if not os.environ.get(var)]
        if missing:
            raise ValueError(
                f"Faltan variables de entorno para MAESTRO_WRITER=azure_devops: {', '.join(missing)}."
            )
        return AzureDevOpsWriter(
            org=os.environ["MAESTRO_AZURE_DEVOPS_ORG"],
            project=os.environ["MAESTRO_AZURE_DEVOPS_PROJECT"],
            pat=os.environ["MAESTRO_AZURE_DEVOPS_PAT"],
            work_item_type=os.environ.get("MAESTRO_AZURE_DEVOPS_WORK_ITEM_TYPE") or "Task",
        )

    raise ValueError(f"Unknown MAESTRO_WRITER: {name}")
