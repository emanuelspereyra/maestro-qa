#!/usr/bin/env python3
"""Audit and safely scaffold project .env files without exposing values."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import urllib.parse
from pathlib import Path
from typing import Any, Iterable


ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ENVIRONMENT_ALIAS = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
ASSIGNMENT = re.compile(
    r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$"
)
TEMPLATE_NAMES = (
    ".env.example",
    ".env.sample",
    ".env.template",
    "env.example",
    "env.sample",
    "env.template",
)
EXCLUDED_DIRECTORIES = {
    ".git",
    ".hg",
    ".svn",
    ".terraform",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "target",
    "vendor",
}
SOURCE_SUFFIXES = {
    ".cs",
    ".go",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".kt",
    ".mjs",
    ".properties",
    ".py",
    ".rb",
    ".rs",
    ".toml",
    ".ts",
    ".tsx",
    ".yaml",
    ".yml",
}
REFERENCE_PATTERNS = (
    re.compile(r"""os\.getenv\(\s*["']([A-Za-z_][A-Za-z0-9_]*)["']"""),
    re.compile(r"""os\.Getenv\(\s*["']([A-Za-z_][A-Za-z0-9_]*)["']"""),
    re.compile(
        r"""os\.environ(?:\.get\(\s*|\[\s*)["']([A-Za-z_][A-Za-z0-9_]*)["']"""
    ),
    re.compile(r"""std::env::var\(\s*["']([A-Za-z_][A-Za-z0-9_]*)["']"""),
    re.compile(r"""ENV\[\s*["']([A-Za-z_][A-Za-z0-9_]*)["']\s*\]"""),
    re.compile(r"""process\.env\.([A-Za-z_][A-Za-z0-9_]*)"""),
    re.compile(
        r"""process\.env\[\s*["']([A-Za-z_][A-Za-z0-9_]*)["']\s*\]"""
    ),
    re.compile(r"""import\.meta\.env\.([A-Za-z_][A-Za-z0-9_]*)"""),
    re.compile(
        r"""(?:System\.getenv|Environment\.GetEnvironmentVariable|Deno\.env\.get)\(\s*["']([A-Za-z_][A-Za-z0-9_]*)["']"""
    ),
    re.compile(
        r"""\$\{([A-Za-z_][A-Za-z0-9_]*)(?:(?::[-+?]|[-+?])[^}]*)?\}"""
    ),
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
SECRET_NAME_PARTS = {
    "api_key",
    "authorization",
    "client_secret",
    "connection",
    "credential",
    "cookie",
    "password",
    "private_key",
    "secret",
    "token",
}
SECRET_EXACT_NAMES = {
    "DATABASE_URL",
    "DB_URL",
    "MONGODB_URI",
    "MONGO_URI",
    "REDIS_URL",
}


class EnvFileError(RuntimeError):
    pass


def qa_required_variables(
    environments: Iterable[str],
    settings: Iterable[str],
) -> set[str]:
    aliases: list[str] = []
    for raw in environments:
        for item in raw.split(","):
            alias = item.strip().lower()
            if not alias:
                continue
            if not ENVIRONMENT_ALIAS.fullmatch(alias):
                raise EnvFileError(f"Invalid QA environment alias: {alias!r}")
            if alias not in aliases:
                aliases.append(alias)

    normalized_settings: list[str] = []
    for raw in settings:
        setting = raw.strip().upper()
        if not ENV_NAME.fullmatch(setting):
            raise EnvFileError(f"Invalid QA setting name: {raw!r}")
        if setting not in normalized_settings:
            normalized_settings.append(setting)

    required: set[str] = set()
    if aliases:
        required.update({"QA_TARGET_ENV", "QA_ALLOWED_ENVIRONMENTS"})
    prefixes: dict[str, str] = {}
    for alias in aliases:
        token = re.sub(r"[^A-Za-z0-9]", "_", alias).upper()
        if token in prefixes and prefixes[token] != alias:
            raise EnvFileError(
                f"QA environments {prefixes[token]!r} and {alias!r} "
                f"share prefix QA_{token}_"
            )
        prefixes[token] = alias
        required.update(f"QA_{token}_{setting}" for setting in normalized_settings)
    return required


def unquote(value: str) -> str:
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {
        '"',
        "'",
    }:
        return stripped[1:-1]
    return stripped


def is_placeholder(value: str | None) -> bool:
    if value is None:
        return True
    normalized = unquote(value).strip().lower()
    return (
        normalized in PLACEHOLDER_VALUES
        or normalized.startswith("<")
        or normalized.startswith("${")
        or normalized.startswith("your_")
        or normalized.startswith("replace_")
    )


def is_secret_name(name: str) -> bool:
    lowered = name.lower()
    uppered = name.upper()
    return (
        uppered in SECRET_EXACT_NAMES
        or uppered.endswith("_DSN")
        or (uppered.endswith("_KEY") and "PUBLIC_KEY" not in uppered)
        or any(part in lowered for part in SECRET_NAME_PARTS)
    )


def value_looks_sensitive(raw_value: str) -> bool:
    value = unquote(raw_value).strip()
    lowered = value.lower()
    if any(
        marker in lowered
        for marker in (
            "accountkey=",
            "api_key=",
            "apikey=",
            "password=",
            "pwd=",
            "secret=",
            "token=",
        )
    ):
        return True
    try:
        parsed = urllib.parse.urlsplit(value)
        return bool(parsed.username or parsed.password)
    except ValueError:
        return True


def parse_env_text(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = ASSIGNMENT.match(line)
        if match:
            values[match.group(1)] = match.group(2).strip()
    return values


def read_env_file(path: Path) -> dict[str, str]:
    try:
        return parse_env_text(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise EnvFileError(f"Unable to read {path}: {exc}") from exc


def dotenv_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def load_env_values(
    path: Path,
    *,
    override: bool = False,
) -> dict[str, str]:
    """Load dotenv assignments without shell evaluation or value logging."""
    if not path.exists():
        return {}
    values = read_env_file(path)
    loaded: dict[str, str] = {}
    for name, raw_value in values.items():
        value = unquote(raw_value)
        if override or name not in os.environ:
            os.environ[name] = value
            loaded[name] = value
    return loaded


def find_template(root: Path, preferred: Iterable[str]) -> Path | None:
    for name in preferred:
        candidate = root / name
        if candidate.is_file():
            return candidate
    return None


def eligible_source(path: Path, max_size: int) -> bool:
    if any(part in EXCLUDED_DIRECTORIES for part in path.parts):
        return False
    if path.name.startswith(".env"):
        return False
    if path.suffix.lower() not in SOURCE_SUFFIXES:
        return False
    try:
        return path.is_file() and path.stat().st_size <= max_size
    except OSError:
        return False


def discover_required_variables(
    root: Path,
    *,
    max_files: int,
    max_file_size: int,
) -> tuple[set[str], dict[str, list[str]]]:
    variables: set[str] = set()
    sources: dict[str, list[str]] = {}
    scanned = 0
    for path in root.rglob("*"):
        if scanned >= max_files:
            break
        if not eligible_source(path, max_file_size):
            continue
        scanned += 1
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pattern in REFERENCE_PATTERNS:
            for match in pattern.finditer(text):
                name = match.group(1)
                variables.add(name)
                references = sources.setdefault(name, [])
                relative = str(path.relative_to(root))
                if relative not in references:
                    references.append(relative)
    return variables, sources


def git_ignores(path: Path, root: Path) -> bool:
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "check-ignore",
                "--quiet",
                "--no-index",
                str(path),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=10,
        )
        if result.returncode == 0:
            return True
    except (OSError, subprocess.TimeoutExpired):
        pass

    gitignore = root / ".gitignore"
    if not gitignore.is_file():
        return False
    try:
        patterns = {
            line.strip()
            for line in gitignore.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
    except OSError:
        return False
    return any(
        pattern in patterns
        for pattern in {".env", "/.env", ".env*", ".env.*", path.name}
    )


def ensure_gitignore(root: Path, env_file: Path) -> bool:
    if git_ignores(env_file, root):
        return True
    gitignore = root / ".gitignore"
    existing = ""
    if gitignore.exists():
        try:
            existing = gitignore.read_text(encoding="utf-8")
        except OSError as exc:
            raise EnvFileError(f"Unable to read {gitignore}: {exc}") from exc
    separator = "" if not existing or existing.endswith("\n") else "\n"
    try:
        gitignore.write_text(
            f"{existing}{separator}.env\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise EnvFileError(f"Unable to update {gitignore}: {exc}") from exc
    return git_ignores(env_file, root)


def render_from_template(
    template: Path | None,
    required: set[str],
) -> str:
    lines: list[str] = []
    existing_names: set[str] = set()
    if template:
        try:
            template_lines = template.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise EnvFileError(f"Unable to read template {template}: {exc}") from exc
        lines.append(f"# Created from {template.name}; secret values were not copied.")
        for line in template_lines:
            match = ASSIGNMENT.match(line)
            if not match:
                lines.append(line)
                continue
            name = match.group(1)
            raw_value = match.group(2)
            existing_names.add(name)
            if is_secret_name(name) or value_looks_sensitive(raw_value):
                lines.append(f"{name}=")
            else:
                lines.append(line)
    else:
        lines.append("# Generated QA environment file. Fill required values locally.")

    missing_names = sorted(required - existing_names)
    if missing_names:
        if lines and lines[-1] != "":
            lines.append("")
        lines.append("# Variables discovered from project usage")
        lines.extend(f"{name}=" for name in missing_names)
    return "\n".join(lines).rstrip() + "\n"


def write_new_env(
    env_file: Path,
    template: Path | None,
    required: set[str],
) -> None:
    if env_file.exists():
        raise EnvFileError(f"Refusing to overwrite existing {env_file}")
    env_file.write_text(
        render_from_template(template, required),
        encoding="utf-8",
    )
    env_file.chmod(0o600)


def materialize_from_process(
    env_file: Path,
    required: set[str],
) -> list[str]:
    try:
        lines = env_file.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise EnvFileError(f"Unable to read {env_file}: {exc}") from exc

    indexes: dict[str, int] = {}
    current: dict[str, str] = {}
    for index, line in enumerate(lines):
        match = ASSIGNMENT.match(line)
        if match:
            indexes[match.group(1)] = index
            current[match.group(1)] = match.group(2).strip()

    materialized: list[str] = []
    for name in sorted(required):
        process_value = os.environ.get(name)
        if not process_value or (
            name in current and not is_placeholder(current[name])
        ):
            continue
        assignment = f"{name}={dotenv_quote(process_value)}"
        if name in indexes:
            lines[indexes[name]] = assignment
        else:
            lines.append(assignment)
        materialized.append(name)

    if materialized:
        env_file.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        env_file.chmod(0o600)
    return materialized


def audit_project(
    root: Path,
    args: argparse.Namespace,
) -> dict[str, Any]:
    root = root.resolve()
    if not root.is_dir():
        raise EnvFileError(f"Project root does not exist: {root}")

    env_file = root / args.env_file_name
    template = find_template(root, args.template_name or TEMPLATE_NAMES)
    template_values = read_env_file(template) if template else {}
    code_required, code_sources = discover_required_variables(
        root,
        max_files=args.max_files,
        max_file_size=args.max_file_size,
    )
    required = (
        set(args.required)
        | set(getattr(args, "qa_required", set()))
        | set(template_values)
        | code_required
    )
    invalid = sorted(name for name in required if not ENV_NAME.fullmatch(name))
    if invalid:
        raise EnvFileError(f"Invalid environment variable names: {invalid}")

    ignored = git_ignores(env_file, root)
    created = False
    gitignore_updated = False
    if not env_file.exists() and args.create:
        if not ignored and args.update_gitignore:
            ignored = ensure_gitignore(root, env_file)
            gitignore_updated = ignored
        if not ignored:
            return {
                "project": str(root),
                "env_file": str(env_file),
                "template": str(template) if template else None,
                "status": "BLOCKED_UNIGNORED",
                "gitignored": False,
                "required_variables": sorted(required),
                "missing_variables": sorted(required),
                "placeholder_variables": [],
                "secret_variables": sorted(
                    name for name in required if is_secret_name(name)
                ),
                "values_exposed": False,
            }
        write_new_env(env_file, template, required)
        created = True

    materialized: list[str] = []
    if env_file.exists() and args.materialize_from_process:
        materialized = materialize_from_process(env_file, required)

    present = read_env_file(env_file) if env_file.exists() else {}
    missing = sorted(name for name in required if name not in present)
    placeholders = sorted(
        name for name in required if name in present and is_placeholder(present[name])
    )
    configured = sorted(
        name for name in required if name in present and not is_placeholder(present[name])
    )
    mode = env_file.stat().st_mode & 0o777 if env_file.exists() else None

    if not env_file.exists():
        status = "MISSING_ENV_FILE"
    elif not ignored:
        status = "UNSAFE_NOT_GITIGNORED"
    elif mode is not None and mode & 0o077:
        status = "UNSAFE_PERMISSIONS"
    elif missing or placeholders:
        status = "CREATED_INCOMPLETE" if created else "INCOMPLETE"
    else:
        status = "READY"

    return {
        "project": str(root),
        "env_file": str(env_file),
        "template": str(template) if template else None,
        "status": status,
        "created": created,
        "gitignored": ignored,
        "gitignore_updated": gitignore_updated,
        "permissions": oct(mode) if mode is not None else None,
        "required_variables": sorted(required),
        "configured_variables": configured,
        "missing_variables": missing,
        "placeholder_variables": placeholders,
        "secret_variables": sorted(
            name for name in required if is_secret_name(name)
        ),
        "materialized_from_process": materialized,
        "code_sources": code_sources,
        "values_exposed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", action="append", type=Path, default=[])
    parser.add_argument("--env-file-name", default=".env")
    parser.add_argument("--template-name", action="append", default=[])
    parser.add_argument("--required", action="append", default=[])
    parser.add_argument(
        "--qa-environment",
        action="append",
        default=[],
        help="Repeat or pass comma-separated aliases",
    )
    parser.add_argument(
        "--qa-setting",
        action="append",
        default=[],
        help="Setting suffix such as FRONTEND_URL or TEST_PASSWORD",
    )
    parser.add_argument("--create", action="store_true")
    parser.add_argument("--update-gitignore", action="store_true")
    parser.add_argument("--materialize-from-process", action="store_true")
    parser.add_argument("--max-files", type=int, default=10_000)
    parser.add_argument("--max-file-size", type=int, default=1_000_000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    projects = args.project or [Path(".")]
    reports: list[dict[str, Any]] = []
    try:
        args.qa_required = qa_required_variables(
            args.qa_environment,
            args.qa_setting,
        )
        for project in projects:
            reports.append(audit_project(project, args))
    except EnvFileError as exc:
        rendered = {
            "status": "ERROR",
            "error": str(exc),
            "values_exposed": False,
        }
        print(json.dumps(rendered, ensure_ascii=False, indent=2))
        return 2

    blocking = [
        report
        for report in reports
        if report["status"]
        not in {
            "READY",
        }
    ]
    result = {
        "status": "READY" if not blocking else "INCOMPLETE",
        "project_count": len(reports),
        "blocking_count": len(blocking),
        "projects": reports,
        "values_exposed": False,
    }
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if not blocking else 1


if __name__ == "__main__":
    raise SystemExit(main())
