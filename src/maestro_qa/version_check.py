import importlib.metadata

import httpx

_RELEASES_URL = "https://api.github.com/repos/emanuelspereyra/maestro-qa/releases/latest"


def installed_version() -> str:
    return importlib.metadata.version("maestro-qa")


def _parse(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.lstrip("v").split("."))


def latest_version() -> str | None:
    """None si no hay releases todavía, no hay red, o cualquier error de la API — este
    chequeo nunca debe romper nada, solo informar cuando puede."""
    try:
        response = httpx.get(_RELEASES_URL, timeout=5, headers={"Accept": "application/vnd.github+json"})
        if response.status_code != 200:
            return None
        tag = response.json().get("tag_name")
        return str(tag).lstrip("v") if tag else None
    except (httpx.HTTPError, ValueError):
        return None


def check_for_update() -> str | None:
    """None si está al día o no se pudo determinar. Nunca aplica el update solo."""
    current = installed_version()
    latest = latest_version()
    if latest is None:
        return None

    try:
        is_newer = _parse(latest) > _parse(current)
    except ValueError:
        return None
    if not is_newer:
        return None

    return (
        f"Hay una versión nueva de Maestro QA disponible: {latest} (tenés {current} instalada). "
        "Actualizá con `git pull` (pip editable) o `uvx --refresh --from <repo> maestro-qa-mcp` (uvx)."
    )
