#!/usr/bin/env python3
"""Run non-destructive, environment-scoped QA preflight checks."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from env_file_manager import (
    EnvFileError,
    git_ignores,
    is_placeholder,
    load_env_values,
)


ENVIRONMENT_ALIAS = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
SETTING_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")
DEFAULT_ALLOWED_ENVIRONMENTS = {"dev", "development", "main", "qa", "staging", "test"}
PRODUCTION_ENVIRONMENTS = {"prod", "production"}
TRUTHY = {"1", "true", "yes", "y", "si", "sí"}
SETTING_TO_ROUTE = {
    "FRONTEND_URL": "frontend_url",
    "API_BASE_URL": "api_base_url",
    "AUTH_URL": "auth_url",
    "ADMIN_URL": "admin_url",
    "OPENAPI_URL": "openapi_url",
}
EXECUTABLE_ROUTE_STATUSES = {"documented", "verified"}


class EnvironmentProfileError(ValueError):
    pass


def is_truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in TRUTHY


def normalize_environment(value: str) -> str:
    environment = value.strip().lower()
    if not ENVIRONMENT_ALIAS.fullmatch(environment):
        raise EnvironmentProfileError(
            f"Invalid QA environment alias {value!r}; use letters, numbers, '-' or '_'."
        )
    return environment


def environment_token(environment: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "_", normalize_environment(environment)).upper()


def allowed_environments() -> set[str]:
    raw = os.environ.get("QA_ALLOWED_ENVIRONMENTS", "")
    if not raw.strip():
        return set(DEFAULT_ALLOWED_ENVIRONMENTS)
    allowed = {
        normalize_environment(value)
        for value in raw.split(",")
        if value.strip()
    }
    if not allowed:
        raise EnvironmentProfileError("QA_ALLOWED_ENVIRONMENTS cannot be empty.")
    prefixes: dict[str, str] = {}
    for environment in allowed:
        token = environment_token(environment)
        if token in prefixes and prefixes[token] != environment:
            raise EnvironmentProfileError(
                f"Environments {prefixes[token]!r} and {environment!r} "
                f"both resolve to QA_{token}_ variables."
            )
        prefixes[token] = environment
    return allowed


def select_environment(argument: str | None) -> str:
    raw = (
        argument
        or os.environ.get("QA_TARGET_ENV")
        or os.environ.get("QA_DEFAULT_ENV")
        or "qa"
    )
    environment = normalize_environment(raw)
    if environment not in allowed_environments():
        raise EnvironmentProfileError(
            f"Environment {environment!r} is not allowed. "
            "Add it to QA_ALLOWED_ENVIRONMENTS."
        )
    if environment in PRODUCTION_ENVIRONMENTS and not is_truthy(
        os.environ.get("QA_ALLOW_PRODUCTION")
    ):
        raise EnvironmentProfileError(
            f"Environment {environment!r} requires QA_ALLOW_PRODUCTION=true."
        )
    return environment


def scoped_variable_name(environment: str, setting: str) -> str:
    normalized_setting = setting.strip().upper()
    if not SETTING_NAME.fullmatch(normalized_setting):
        raise EnvironmentProfileError(f"Invalid QA setting name {setting!r}.")
    return f"QA_{environment_token(environment)}_{normalized_setting}"


def resolve_setting(
    environment: str,
    setting: str,
) -> tuple[str | None, str]:
    scoped_name = scoped_variable_name(environment, setting)
    scoped_value = os.environ.get(scoped_name)
    if scoped_value is not None and not is_placeholder(scoped_value):
        return scoped_value, scoped_name

    generic_name = f"QA_{setting.strip().upper()}"
    if is_truthy(os.environ.get("QA_ALLOW_GENERIC_ENV_FALLBACK")):
        generic_value = os.environ.get(generic_name)
        if generic_value is not None and not is_placeholder(generic_value):
            return generic_value, generic_name
    return None, scoped_name


def sanitized_url(url: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(url)
        safe_host = parsed.hostname or ""
        if parsed.port:
            safe_host = f"{safe_host}:{parsed.port}"
        return urllib.parse.urlunsplit(
            (parsed.scheme, safe_host, parsed.path, "", "")
        )
    except ValueError:
        return "<invalid-url>"


def base_url_is_safe(url: str) -> bool:
    try:
        parsed = urllib.parse.urlsplit(url)
        return (
            parsed.scheme.lower() in {"http", "https"}
            and bool(parsed.hostname)
            and not parsed.username
            and not parsed.password
            and not parsed.query
            and not parsed.fragment
        )
    except ValueError:
        return False


def normalized_route_url(url: str) -> str:
    return sanitized_url(url).rstrip("/")


def load_route_catalog(path: Path) -> dict[str, Any]:
    try:
        catalog = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise EnvironmentProfileError(
            f"Unable to read route catalog {path}: {exc.strerror or type(exc).__name__}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise EnvironmentProfileError(
            f"Invalid JSON in route catalog {path}: line {exc.lineno}"
        ) from exc
    if not isinstance(catalog, dict) or not isinstance(
        catalog.get("environments"), dict
    ):
        raise EnvironmentProfileError(
            f"Route catalog {path} requires an environments object."
        )
    return catalog


def route_catalog_checks(
    catalog: dict[str, Any],
    environment: str,
    resolved_settings: dict[str, tuple[str | None, str]],
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    profile = catalog["environments"].get(environment)
    if not isinstance(profile, dict):
        return [
            {
                "kind": "environment-route-catalog",
                "target": environment,
                "ok": False,
                "error": "Environment is missing from the route catalog.",
            }
        ]
    routes = profile.get("routes")
    if not isinstance(routes, dict):
        return [
            {
                "kind": "environment-route-catalog",
                "target": environment,
                "ok": False,
                "error": "Environment profile requires a routes object.",
            }
        ]

    for setting, (runtime_url, source) in resolved_settings.items():
        route_type = SETTING_TO_ROUTE.get(setting)
        if not route_type:
            continue
        entry = routes.get(route_type)
        if not isinstance(entry, dict):
            checks.append(
                {
                    "kind": "environment-route-catalog",
                    "target": f"{environment}.{route_type}",
                    "source": source,
                    "ok": False,
                    "error": "Required route is missing from the catalog.",
                }
            )
            continue

        status = str(entry.get("status", "missing"))
        documented_url = str(entry.get("url", ""))
        route_ok = (
            status in EXECUTABLE_ROUTE_STATUSES
            and bool(runtime_url)
            and bool(documented_url)
            and base_url_is_safe(runtime_url)
            and base_url_is_safe(documented_url)
            and normalized_route_url(runtime_url)
            == normalized_route_url(documented_url)
        )
        error = None
        if status not in EXECUTABLE_ROUTE_STATUSES:
            error = f"Route status {status!r} is not executable."
        elif not documented_url:
            error = "The catalog route has no URL."
        elif not runtime_url:
            error = "The environment variable has no URL."
        elif not base_url_is_safe(runtime_url) or not base_url_is_safe(documented_url):
            error = (
                "Base URLs must use HTTP(S) and cannot contain credentials, "
                "query parameters or fragments."
            )
        elif not route_ok:
            error = "Runtime URL differs from the documented route."
        checks.append(
            {
                "kind": "environment-route",
                "target": f"{environment}.{route_type}",
                "source": source,
                "catalog_status": status,
                "catalog_url": normalized_route_url(documented_url)
                if documented_url
                else "",
                "ok": route_ok,
                **({"error": error} if error else {}),
            }
        )
    return checks


def http_check(url: str, timeout: float, source: str) -> dict[str, Any]:
    safe_target = sanitized_url(url)
    if not base_url_is_safe(url):
        return {
            "kind": "http",
            "target": safe_target,
            "source": source,
            "ok": False,
            "error": "UnsafeBaseURL",
        }
    try:
        request = urllib.request.Request(
            url,
            method="HEAD",
            headers={"User-Agent": "qa-preflight/1.0"},
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return {
                "kind": "http",
                "target": safe_target,
                "source": source,
                "ok": 200 <= response.status < 500,
                "status": response.status,
            }
    except urllib.error.HTTPError as exc:
        return {
            "kind": "http",
            "target": safe_target,
            "source": source,
            "ok": exc.code < 500,
            "status": exc.code,
            "error": "HTTPError",
        }
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        return {
            "kind": "http",
            "target": safe_target,
            "source": source,
            "ok": False,
            "error": type(exc).__name__,
        }


def write_report(report: dict[str, Any], output: Path | None) -> None:
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--environment",
        help="Overrides QA_TARGET_ENV for this preflight",
    )
    parser.add_argument("--frontend-url")
    parser.add_argument("--api-url")
    parser.add_argument("--require-frontend", action="store_true")
    parser.add_argument("--require-api", action="store_true")
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(os.environ.get("QA_ENV_FILE", ".env")),
    )
    parser.add_argument("--require-env-file", action="store_true")
    parser.add_argument(
        "--route-catalog",
        type=Path,
        default=Path("qa-knowledge/environment-routes.json"),
    )
    parser.add_argument("--require-route-catalog", action="store_true")
    parser.add_argument(
        "--required-setting",
        action="append",
        default=[],
        help="Environment-scoped suffix such as TEST_USERNAME or DB_READ_CONNECTION",
    )
    parser.add_argument("--required-env", action="append", default=[])
    parser.add_argument("--required-path", action="append", default=[])
    parser.add_argument("--required-command", action="append", default=[])
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    env_file_error: str | None = None
    env_file_loaded_count = 0
    if args.env_file.exists():
        try:
            env_file_loaded_count = len(load_env_values(args.env_file))
        except (EnvFileError, OSError) as exc:
            env_file_error = type(exc).__name__

    try:
        environment = select_environment(args.environment)
    except EnvironmentProfileError as exc:
        write_report(
            {
                "environment": args.environment
                or os.environ.get("QA_TARGET_ENV")
                or os.environ.get("QA_DEFAULT_ENV")
                or "qa",
                "status": "BLOCKED_ENVIRONMENT",
                "check_count": 1,
                "failed_count": 1,
                "checks": [
                    {
                        "kind": "environment",
                        "target": "QA_TARGET_ENV",
                        "ok": False,
                        "error": str(exc),
                    }
                ],
            },
            args.output,
        )
        return 2

    checks: list[dict[str, Any]] = [
        {
            "kind": "environment",
            "target": environment,
            "variable_prefix": f"QA_{environment_token(environment)}_",
            "ok": True,
        }
    ]
    if args.env_file.exists():
        try:
            mode = args.env_file.stat().st_mode & 0o777
        except OSError:
            mode = 0
        ignored = git_ignores(args.env_file, args.env_file.parent)
        env_file_issues: list[str] = []
        if env_file_error:
            env_file_issues.append(env_file_error)
        if mode & 0o077:
            env_file_issues.append("Environment file permissions must be 0600.")
        if not ignored:
            env_file_issues.append("Environment file is not ignored by Git.")
        env_file_ok = (
            env_file_error is None
            and mode & 0o077 == 0
            and ignored
        )
        checks.append(
            {
                "kind": "environment-file",
                "target": str(args.env_file),
                "ok": env_file_ok,
                "permissions": oct(mode),
                "gitignored": ignored,
                "loaded_variable_count": env_file_loaded_count,
                **(
                    {"error": " ".join(env_file_issues)}
                    if env_file_issues
                    else {}
                ),
            }
        )
    elif args.require_env_file:
        checks.append(
            {
                "kind": "environment-file",
                "target": str(args.env_file),
                "ok": False,
                "error": "Required .env file does not exist.",
            }
        )

    for name in args.required_env:
        checks.append(
            {
                "kind": "environment-variable",
                "target": name,
                "ok": (
                    os.environ.get(name) is not None
                    and not is_placeholder(os.environ.get(name))
                ),
            }
        )

    requested_settings = list(args.required_setting)
    if args.require_frontend:
        requested_settings.append("FRONTEND_URL")
    if args.require_api:
        requested_settings.append("API_BASE_URL")

    resolved_settings: dict[str, tuple[str | None, str]] = {}
    try:
        for setting in requested_settings:
            normalized = setting.strip().upper()
            if normalized in resolved_settings:
                continue
            resolved = resolve_setting(environment, normalized)
            resolved_settings[normalized] = resolved
            value, source = resolved
            checks.append(
                {
                    "kind": "environment-setting",
                    "target": normalized,
                    "source": source,
                    "ok": bool(value),
                }
            )
    except EnvironmentProfileError as exc:
        checks.append(
            {
                "kind": "environment-setting",
                "target": setting,
                "ok": False,
                "error": str(exc),
            }
        )

    route_catalog: dict[str, Any] | None = None
    if args.route_catalog.exists():
        try:
            route_catalog = load_route_catalog(args.route_catalog)
            checks.append(
                {
                    "kind": "environment-route-catalog",
                    "target": str(args.route_catalog),
                    "ok": True,
                }
            )
        except EnvironmentProfileError as exc:
            checks.append(
                {
                    "kind": "environment-route-catalog",
                    "target": str(args.route_catalog),
                    "ok": False,
                    "error": str(exc),
                }
            )
    elif args.require_route_catalog:
        checks.append(
            {
                "kind": "environment-route-catalog",
                "target": str(args.route_catalog),
                "ok": False,
                "error": "Route catalog is required but does not exist.",
            }
        )
    if route_catalog is not None:
        checks.extend(
            route_catalog_checks(
                route_catalog,
                environment,
                resolved_settings,
            )
        )
    route_catalog_blocked = any(
        not check["ok"]
        and check["kind"] in {"environment-route", "environment-route-catalog"}
        for check in checks
    )

    for raw_path in args.required_path:
        path = Path(raw_path)
        checks.append(
            {
                "kind": "path",
                "target": raw_path,
                "ok": path.exists(),
                "type": (
                    "directory" if path.is_dir() else "file" if path.is_file() else None
                ),
            }
        )
    for command in args.required_command:
        resolved = shutil.which(command)
        checks.append(
            {
                "kind": "command",
                "target": command,
                "ok": resolved is not None,
                "resolved": resolved,
            }
        )

    frontend_value, frontend_source = (
        (args.frontend_url, "argument:--frontend-url")
        if args.frontend_url
        else resolved_settings.get(
            "FRONTEND_URL",
            resolve_setting(environment, "FRONTEND_URL"),
        )
    )
    api_value, api_source = (
        (args.api_url, "argument:--api-url")
        if args.api_url
        else resolved_settings.get(
            "API_BASE_URL",
            resolve_setting(environment, "API_BASE_URL"),
        )
    )
    if frontend_value and not route_catalog_blocked:
        checks.append(http_check(frontend_value, args.timeout, frontend_source))
    if api_value and not route_catalog_blocked:
        checks.append(http_check(api_value, args.timeout, api_source))

    failed = [check for check in checks if not check["ok"]]
    environment_blocked = any(
        not check["ok"]
        and check["kind"] in {"environment-route", "environment-route-catalog"}
        for check in checks
    )
    report = {
        "environment": environment,
        "variable_prefix": f"QA_{environment_token(environment)}_",
        "status": (
            "READY"
            if not failed
            else "BLOCKED_ENVIRONMENT"
            if environment_blocked
            else "BLOCKED_PREFLIGHT"
        ),
        "check_count": len(checks),
        "failed_count": len(failed),
        "checks": checks,
    }
    write_report(report, args.output)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
