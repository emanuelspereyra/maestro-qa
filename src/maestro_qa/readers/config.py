import os

from .azure_devops import AzureDevOpsReader
from .base import Reader

# Mismas credenciales que el writer (spec 027) — un solo org/project de Azure DevOps,
# MAESTRO_READER habilita la lectura independientemente de si el writer está activo.
_AZURE_DEVOPS_REQUIRED_VARS = ("MAESTRO_AZURE_DEVOPS_ORG", "MAESTRO_AZURE_DEVOPS_PROJECT", "MAESTRO_AZURE_DEVOPS_PAT")


def get_reader() -> Reader | None:
    """None si MAESTRO_READER no está seteada — leer de un sistema externo es opcional."""
    name = os.environ.get("MAESTRO_READER", "").strip().lower()
    if not name:
        return None

    if name == "azure_devops":
        missing = [var for var in _AZURE_DEVOPS_REQUIRED_VARS if not os.environ.get(var)]
        if missing:
            raise ValueError(f"Faltan variables de entorno para MAESTRO_READER=azure_devops: {', '.join(missing)}.")
        return AzureDevOpsReader(
            org=os.environ["MAESTRO_AZURE_DEVOPS_ORG"],
            project=os.environ["MAESTRO_AZURE_DEVOPS_PROJECT"],
            pat=os.environ["MAESTRO_AZURE_DEVOPS_PAT"],
        )

    raise ValueError(f"Unknown MAESTRO_READER: {name}")
