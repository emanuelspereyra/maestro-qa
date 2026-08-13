"""Resolve a safe, environment-scoped QA execution profile."""

from __future__ import annotations

import os
import re
from pathlib import Path


ENVIRONMENT_ALIAS = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
SETTING_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")
DEFAULT_ALLOWED_ENVIRONMENTS = ("dev", "development", "main", "qa", "staging", "test")
PRODUCTION_ENVIRONMENTS = {"prod", "production"}
TRUTHY = {"1", "true", "yes", "y", "si", "sí"}
ENV_ASSIGNMENT = re.compile(
    r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$"
)
PLACEHOLDER_VALUES = {
    "",
    "changeme",
    "change_me",
    "change-me",
    "example",
    "placeholder",
    "replace_me",
    "replace-me",
    "todo",
    "your_value",
    "your-value",
}
_LOADED_ENV_FILES: set[Path] = set()


class QAEnvironmentError(ValueError):
    """Raised when an execution profile is missing or unsafe."""


def is_truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in TRUTHY


def unquote_env_value(value: str) -> str:
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {
        '"',
        "'",
    }:
        return stripped[1:-1]
    return stripped


def is_configured_value(value: str | None) -> bool:
    if value is None:
        return False
    normalized = unquote_env_value(value).strip().lower()
    return not (
        normalized in PLACEHOLDER_VALUES
        or normalized.startswith("<")
        or normalized.startswith("${")
        or normalized.startswith("your_")
        or normalized.startswith("replace_")
    )


def load_env_file(path: str | Path | None = None) -> list[str]:
    """Load .env assignments without shell evaluation or value logging."""
    selected = Path(path or os.environ.get("QA_ENV_FILE", ".env")).resolve()
    if selected in _LOADED_ENV_FILES or not selected.exists():
        return []
    try:
        if not selected.is_file() or selected.stat().st_size > 1_000_000:
            raise QAEnvironmentError(f"Unsafe or oversized environment file: {selected}")
        text = selected.read_text(encoding="utf-8")
    except OSError as exc:
        raise QAEnvironmentError(
            f"Unable to read environment file {selected}: {type(exc).__name__}"
        ) from exc

    loaded: list[str] = []
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = ENV_ASSIGNMENT.match(line)
        if not match:
            continue
        name, raw_value = match.groups()
        if name not in os.environ:
            os.environ[name] = unquote_env_value(raw_value)
            loaded.append(name)
    _LOADED_ENV_FILES.add(selected)
    return loaded


def normalize_environment(value: str) -> str:
    environment = value.strip().lower()
    if not ENVIRONMENT_ALIAS.fullmatch(environment):
        raise QAEnvironmentError(
            f"Invalid QA environment alias {value!r}; use letters, numbers, '-' or '_'."
        )
    return environment


def environment_token(environment: str) -> str:
    normalized = normalize_environment(environment)
    return re.sub(r"[^A-Za-z0-9]", "_", normalized).upper()


def allowed_environments() -> set[str]:
    raw = os.environ.get("QA_ALLOWED_ENVIRONMENTS", "")
    values = raw.split(",") if raw.strip() else DEFAULT_ALLOWED_ENVIRONMENTS
    allowed = {normalize_environment(value) for value in values if value.strip()}
    if not allowed:
        raise QAEnvironmentError("QA_ALLOWED_ENVIRONMENTS cannot be empty.")
    prefixes: dict[str, str] = {}
    for environment in allowed:
        token = environment_token(environment)
        if token in prefixes and prefixes[token] != environment:
            raise QAEnvironmentError(
                f"Environments {prefixes[token]!r} and {environment!r} "
                f"both resolve to QA_{token}_ variables."
            )
        prefixes[token] = environment
    return allowed


def target_environment() -> str:
    load_env_file()
    selected = os.environ.get("QA_TARGET_ENV") or os.environ.get(
        "QA_DEFAULT_ENV", "qa"
    )
    environment = normalize_environment(selected)
    allowed = allowed_environments()
    if environment not in allowed:
        raise QAEnvironmentError(
            f"Environment {environment!r} is not allowed. "
            "Add it to QA_ALLOWED_ENVIRONMENTS."
        )
    if environment in PRODUCTION_ENVIRONMENTS and not is_truthy(
        os.environ.get("QA_ALLOW_PRODUCTION")
    ):
        raise QAEnvironmentError(
            f"Environment {environment!r} requires QA_ALLOW_PRODUCTION=true."
        )
    return environment


def variable_name(setting: str, environment: str) -> str:
    normalized_setting = setting.strip().upper()
    if not SETTING_NAME.fullmatch(normalized_setting):
        raise QAEnvironmentError(f"Invalid QA setting name {setting!r}.")
    return f"QA_{environment_token(environment)}_{normalized_setting}"


def resolve_setting_with_source(
    setting: str,
    environment: str | None = None,
    *,
    required: bool = True,
) -> tuple[str | None, str]:
    selected = normalize_environment(environment) if environment else target_environment()
    scoped_name = variable_name(setting, selected)
    scoped_value = os.environ.get(scoped_name)
    if is_configured_value(scoped_value):
        return scoped_value, scoped_name

    generic_name = f"QA_{setting.strip().upper()}"
    if is_truthy(os.environ.get("QA_ALLOW_GENERIC_ENV_FALLBACK")):
        generic_value = os.environ.get(generic_name)
        if is_configured_value(generic_value):
            return generic_value, generic_name

    if required:
        fallback_hint = (
            f" or {generic_name} with QA_ALLOW_GENERIC_ENV_FALLBACK=true"
        )
        raise QAEnvironmentError(
            f"Missing {scoped_name}{fallback_hint}."
        )
    return None, scoped_name


def resolve_setting(
    setting: str,
    environment: str | None = None,
    *,
    required: bool = True,
) -> str | None:
    value, _ = resolve_setting_with_source(
        setting,
        environment,
        required=required,
    )
    return value
