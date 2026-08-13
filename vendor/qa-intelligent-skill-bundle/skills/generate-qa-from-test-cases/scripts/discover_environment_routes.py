#!/usr/bin/env python3
"""Find documented environment URL candidates without reading secret env files."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import urllib.parse
from pathlib import Path
from typing import Any, Iterable


DEFAULT_ENVIRONMENTS = ("dev", "development", "main", "qa", "staging", "test")
ENVIRONMENT_ALIAS = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
URL_PATTERN = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
TEXT_SUFFIXES = {
    ".conf",
    ".config",
    ".ini",
    ".json",
    ".md",
    ".properties",
    ".rst",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
SAFE_ENV_FILENAMES = {
    ".env.example",
    ".env.sample",
    ".env.template",
    "env.example",
    "env.sample",
    "env.template",
}
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
ROUTE_TYPES = (
    "frontend_url",
    "api_base_url",
    "auth_url",
    "admin_url",
    "openapi_url",
)


class DiscoveryError(ValueError):
    pass


def normalize_environment(value: str) -> str:
    environment = value.strip().lower()
    if not ENVIRONMENT_ALIAS.fullmatch(environment):
        raise DiscoveryError(
            f"Invalid environment alias {value!r}; "
            "use letters, numbers, '-' or '_'."
        )
    return environment


def environment_token(environment: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "_", environment).upper()


def parse_environments(values: Iterable[str]) -> list[str]:
    environments: list[str] = []
    for raw in values:
        for item in raw.split(","):
            if not item.strip():
                continue
            environment = normalize_environment(item)
            if environment not in environments:
                environments.append(environment)
    if not environments:
        environments = list(DEFAULT_ENVIRONMENTS)

    tokens: dict[str, str] = {}
    for environment in environments:
        token = environment_token(environment)
        if token in tokens and tokens[token] != environment:
            raise DiscoveryError(
                f"Environments {tokens[token]!r} and {environment!r} "
                f"both map to QA_{token}_ variables."
            )
        tokens[token] = environment
    return environments


def sanitize_url(raw_url: str) -> str | None:
    candidate = raw_url.rstrip(".,;:)]}")
    try:
        parsed = urllib.parse.urlsplit(candidate)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            return None
        host = parsed.hostname
        if parsed.port:
            host = f"{host}:{parsed.port}"
        return urllib.parse.urlunsplit(
            (parsed.scheme.lower(), host, parsed.path.rstrip("/"), "", "")
        )
    except ValueError:
        return None


def eligible_file(path: Path, max_size: int) -> bool:
    if any(part in EXCLUDED_DIRECTORIES for part in path.parts):
        return False
    if path.name.startswith(".env") and path.name not in SAFE_ENV_FILENAMES:
        return False
    if path.name in SAFE_ENV_FILENAMES:
        return True
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return False
    try:
        return path.is_file() and path.stat().st_size <= max_size
    except OSError:
        return False


def classify_route(url: str, context: str) -> str | None:
    lowered = f"{url} {context}".lower()
    if any(term in lowered for term in ("openapi", "swagger", "api-docs")):
        return "openapi_url"
    if any(term in lowered for term in ("issuer", "oauth", "oidc", "auth_url")):
        return "auth_url"
    if any(term in lowered for term in ("admin_url", "admin-ui", "backoffice")):
        return "admin_url"
    parsed = urllib.parse.urlsplit(url)
    hostname = parsed.hostname or ""
    if (
        hostname.startswith("api.")
        or "/api" in parsed.path.lower()
        or any(
            term in lowered
            for term in (
                "api_base",
                "api-url",
                "api_url",
                "backend_url",
                "server.url",
            )
        )
    ):
        return "api_base_url"
    if any(
        term in lowered
        for term in (
            "frontend",
            "front_url",
            "web_url",
            "app_url",
            "site_url",
            "base_url",
        )
    ):
        return "frontend_url"
    return None


def environment_pattern(environment: str) -> re.Pattern[str]:
    return re.compile(
        rf"(?<![a-z0-9]){re.escape(environment.lower())}(?![a-z0-9])",
        re.IGNORECASE,
    )


def classify_environment(
    url: str,
    context: str,
    environments: list[str],
) -> str | None:
    haystack = f"{url} {context}".lower()
    matches = [
        environment
        for environment in environments
        if environment_pattern(environment).search(haystack)
    ]
    if len(matches) == 1:
        return matches[0]
    if "localhost" in haystack or "127.0.0.1" in haystack:
        for local_name in ("dev", "development", "test"):
            if local_name in environments:
                return local_name
    return None


def route_entry(environment: str, route_type: str) -> dict[str, Any]:
    suffix = {
        "frontend_url": "FRONTEND_URL",
        "api_base_url": "API_BASE_URL",
        "auth_url": "AUTH_URL",
        "admin_url": "ADMIN_URL",
        "openapi_url": "OPENAPI_URL",
    }[route_type]
    return {
        "status": "missing",
        "url": "",
        "variable": f"QA_{environment_token(environment)}_{suffix}",
        "sources": [],
        "alternatives": [],
    }


def empty_catalog(environments: list[str]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "generated_at": dt.datetime.now(dt.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "environments": {
            environment: {
                "status": "incomplete",
                "routes": {
                    route_type: route_entry(environment, route_type)
                    for route_type in ROUTE_TYPES
                },
            }
            for environment in environments
        },
        "unassigned_candidates": [],
        "scan": {"roots": [], "files_scanned": 0, "files_skipped": 0},
    }


def load_existing_catalog(
    path: Path,
    environments: list[str],
) -> dict[str, Any]:
    catalog = empty_catalog(environments)
    if not path.exists():
        return catalog
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DiscoveryError(f"Unable to read existing catalog {path}: {exc}") from exc
    if not isinstance(existing, dict) or not isinstance(
        existing.get("environments"), dict
    ):
        raise DiscoveryError(
            f"Existing catalog {path} requires an environments object."
        )

    for environment, existing_profile in existing["environments"].items():
        if not isinstance(existing_profile, dict):
            continue
        normalized = normalize_environment(environment)
        if normalized not in catalog["environments"]:
            catalog["environments"][normalized] = {
                "status": "incomplete",
                "routes": {
                    route_type: route_entry(normalized, route_type)
                    for route_type in ROUTE_TYPES
                },
            }
        profile = catalog["environments"][normalized]
        profile["status"] = existing_profile.get("status", profile["status"])
        existing_routes = existing_profile.get("routes", {})
        if not isinstance(existing_routes, dict):
            continue
        for route_type in ROUTE_TYPES:
            existing_entry = existing_routes.get(route_type)
            if isinstance(existing_entry, dict):
                merged = route_entry(normalized, route_type)
                merged.update(existing_entry)
                profile["routes"][route_type] = merged
    if isinstance(existing.get("unassigned_candidates"), list):
        catalog["unassigned_candidates"] = existing["unassigned_candidates"]
    return catalog


def add_candidate(
    catalog: dict[str, Any],
    *,
    environment: str | None,
    route_type: str | None,
    url: str,
    source: dict[str, Any],
) -> None:
    if not environment or not route_type:
        candidate = {
            "environment": environment or "unknown",
            "route_type": route_type or "unknown",
            "url": url,
            "source": source,
        }
        if candidate not in catalog["unassigned_candidates"]:
            catalog["unassigned_candidates"].append(candidate)
        return

    entry = catalog["environments"][environment]["routes"][route_type]
    if not entry["url"]:
        entry["url"] = url
        entry["status"] = "candidate"
        entry["sources"].append(source)
    elif entry["url"] == url:
        if source not in entry["sources"]:
            entry["sources"].append(source)
    else:
        alternative = {"url": url, "source": source}
        if alternative not in entry["alternatives"]:
            entry["alternatives"].append(alternative)
        entry["status"] = "conflict"


def scan_file(
    path: Path,
    root: Path,
    environments: list[str],
    catalog: dict[str, Any],
) -> None:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        catalog["scan"]["files_skipped"] += 1
        return

    catalog["scan"]["files_scanned"] += 1
    lines = text.splitlines()
    for index, line in enumerate(lines, start=1):
        for match in URL_PATTERN.finditer(line):
            url = sanitize_url(match.group(0))
            if not url:
                continue
            relative = str(path.relative_to(root))
            context = f"{relative} {line[:500]}"
            route_type = classify_route(url, context)
            environment = classify_environment(url, context, environments)
            add_candidate(
                catalog,
                environment=environment,
                route_type=route_type,
                url=url,
                source={
                    "type": "local-file",
                    "path": str(path),
                    "line": index,
                },
            )


def update_statuses(catalog: dict[str, Any]) -> None:
    for profile in catalog["environments"].values():
        required = [
            profile["routes"]["frontend_url"]["status"],
            profile["routes"]["api_base_url"]["status"],
        ]
        if any(status == "conflict" for status in required):
            profile["status"] = "conflict"
        elif all(status in {"documented", "verified"} for status in required):
            profile["status"] = "complete"
        elif all(
            status in {"candidate", "documented", "verified"}
            for status in required
        ):
            profile["status"] = "candidates-found"
        else:
            profile["status"] = "incomplete"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", action="append", type=Path, default=[])
    parser.add_argument(
        "--environment",
        action="append",
        default=[],
        help="Repeat or pass comma-separated aliases",
    )
    parser.add_argument("--max-file-size", type=int, default=1_000_000)
    parser.add_argument("--max-files", type=int, default=10_000)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("qa-knowledge/environment-routes.json"),
    )
    args = parser.parse_args()

    try:
        configured = args.environment or [
            os.environ.get("QA_ALLOWED_ENVIRONMENTS", "")
        ]
        environments = parse_environments(configured)
    except DiscoveryError as exc:
        parser.error(str(exc))

    roots = [path.resolve() for path in (args.root or [Path(".")])]
    try:
        catalog = load_existing_catalog(args.output, environments)
    except DiscoveryError as exc:
        parser.error(str(exc))
    catalog["generated_at"] = (
        dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    )
    catalog["scan"] = {"roots": [], "files_scanned": 0, "files_skipped": 0}
    catalog["scan"]["roots"] = [str(root) for root in roots]

    visited = 0
    for root in roots:
        if not root.exists():
            catalog["scan"]["files_skipped"] += 1
            continue
        candidates = [root] if root.is_file() else root.rglob("*")
        for path in candidates:
            if visited >= args.max_files:
                catalog["scan"]["truncated"] = True
                break
            if not eligible_file(path, args.max_file_size):
                continue
            visited += 1
            scan_file(path, root if root.is_dir() else root.parent, environments, catalog)

    update_statuses(catalog)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": "CANDIDATES_DISCOVERED",
                "output": str(args.output),
                "environments": environments,
                "files_scanned": catalog["scan"]["files_scanned"],
                "unassigned_candidates": len(catalog["unassigned_candidates"]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
