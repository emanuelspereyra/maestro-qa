#!/usr/bin/env python3
"""Create a non-secret qa-project.yaml through a conditional interview."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import urllib.parse
from pathlib import Path
from typing import Any


ENVIRONMENT_ALIAS = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
ROUTE_TYPES = (
    "frontend_url",
    "api_base_url",
    "auth_url",
    "admin_url",
    "openapi_url",
)
ROUTE_LABELS = {
    "frontend_url": "frontend",
    "api_base_url": "API base",
    "auth_url": "autenticación o issuer, si aplica",
    "admin_url": "administración, si aplica",
    "openapi_url": "OpenAPI o Swagger, si aplica",
}
ROUTE_SUFFIXES = {
    "frontend_url": "FRONTEND_URL",
    "api_base_url": "API_BASE_URL",
    "auth_url": "AUTH_URL",
    "admin_url": "ADMIN_URL",
    "openapi_url": "OPENAPI_URL",
}


def ask_text(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or default


def ask_bool(prompt: str, default: bool = False) -> bool:
    label = "S/n" if default else "s/N"
    while True:
        value = input(f"{prompt} [{label}]: ").strip().lower()
        if not value:
            return default
        if value in {"s", "si", "sí", "y", "yes"}:
            return True
        if value in {"n", "no"}:
            return False
        print("Responder sí o no.")


def ask_choice(prompt: str, choices: list[str], default: str) -> str:
    rendered = "/".join(choices)
    while True:
        value = ask_text(f"{prompt} ({rendered})", default)
        if value in choices:
            return value
        print(f"Elegir una opción válida: {rendered}")


def parse_environment_aliases(raw: str, default: str) -> list[str]:
    aliases: list[str] = []
    for value in [default, *raw.split(",")]:
        alias = value.strip().lower()
        if not alias or alias in aliases:
            continue
        if not ENVIRONMENT_ALIAS.fullmatch(alias):
            raise ValueError(
                f"Alias de ambiente inválido: {alias!r}. "
                "Usar letras, números, guion o guion bajo."
            )
        aliases.append(alias)

    prefixes: dict[str, str] = {}
    for alias in aliases:
        prefix = re.sub(r"[^A-Za-z0-9]", "_", alias).upper()
        if prefix in prefixes and prefixes[prefix] != alias:
            raise ValueError(
                f"Los ambientes {prefixes[prefix]!r} y {alias!r} generan "
                f"el mismo prefijo QA_{prefix}_"
            )
        prefixes[prefix] = alias
    return aliases


def ask_environment_aliases(default: str) -> list[str]:
    while True:
        raw = ask_text(
            "Ambientes permitidos para automatización, separados por coma",
            default,
        )
        try:
            return parse_environment_aliases(raw, default)
        except ValueError as exc:
            print(exc)


def environment_token(environment: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "_", environment).upper()


def validate_base_url(value: str) -> str:
    if not value:
        return ""
    try:
        parsed = urllib.parse.urlsplit(value)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            raise ValueError("la URL debe usar http o https e incluir un host")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError(
                "la URL base no puede incluir credenciales, query ni fragmento"
            )
        host = parsed.hostname
        if parsed.port:
            host = f"{host}:{parsed.port}"
        return urllib.parse.urlunsplit(
            (parsed.scheme.lower(), host, parsed.path.rstrip("/"), "", "")
        )
    except ValueError as exc:
        raise ValueError(f"URL inválida: {exc}") from exc


def ask_url(prompt: str, default: str = "") -> str:
    while True:
        value = ask_text(prompt, default)
        try:
            return validate_base_url(value)
        except ValueError as exc:
            print(exc)


def new_route_entry(environment: str, route_type: str) -> dict[str, Any]:
    return {
        "status": "missing",
        "url": "",
        "variable": (
            f"QA_{environment_token(environment)}_{ROUTE_SUFFIXES[route_type]}"
        ),
        "sources": [],
        "alternatives": [],
    }


def load_route_catalog(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "schema_version": 1,
            "generated_at": "",
            "environments": {},
            "unassigned_candidates": [],
            "scan": {"roots": [], "files_scanned": 0, "files_skipped": 0},
        }
    try:
        catalog = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"No se pudo leer el catálogo de rutas {path}: {exc}") from exc
    if not isinstance(catalog, dict) or not isinstance(
        catalog.get("environments"), dict
    ):
        raise ValueError(
            f"El catálogo {path} debe contener un objeto environments"
        )
    return catalog


def ensure_route_profiles(
    catalog: dict[str, Any],
    environments: list[str],
) -> None:
    profiles = catalog.setdefault("environments", {})
    for environment in environments:
        profile = profiles.setdefault(
            environment,
            {"status": "incomplete", "routes": {}},
        )
        routes = profile.setdefault("routes", {})
        for route_type in ROUTE_TYPES:
            existing = routes.get(route_type)
            if not isinstance(existing, dict):
                routes[route_type] = new_route_entry(environment, route_type)
                continue
            default = new_route_entry(environment, route_type)
            for key, value in default.items():
                existing.setdefault(key, value)


def configure_environment_routes(
    catalog: dict[str, Any],
    environments: list[str],
) -> None:
    ensure_route_profiles(catalog, environments)
    required = {"frontend_url", "api_base_url"}

    for environment in environments:
        print(f"Rutas del ambiente {environment}:")
        profile = catalog["environments"][environment]
        for route_type in ROUTE_TYPES:
            entry = profile["routes"][route_type]
            current_url = str(entry.get("url", ""))
            current_status = str(entry.get("status", "missing"))

            if current_status == "not-applicable" and route_type not in required:
                print(
                    f"{ROUTE_LABELS[route_type].capitalize()} de {environment}: "
                    "no aplica según el catálogo."
                )
                continue

            if current_url:
                try:
                    current_url = validate_base_url(current_url)
                    entry["url"] = current_url
                except ValueError:
                    entry["url"] = ""
                    entry["status"] = "conflict"
                    current_url = ""

            if current_url and current_status in {"documented", "verified"}:
                print(
                    f"Encontrada {ROUTE_LABELS[route_type]} en el catálogo: "
                    f"{current_url}"
                )
                continue

            if current_url and current_status == "candidate":
                if ask_bool(
                    f"¿Confirmás {current_url} como {ROUTE_LABELS[route_type]} "
                    f"de {environment}?"
                ):
                    entry["status"] = "documented"
                    entry.setdefault("sources", []).append(
                        {"type": "user-confirmation"}
                    )
                    continue

            value = ask_url(
                f"URL de {ROUTE_LABELS[route_type]} para {environment}"
            )
            if value:
                entry["url"] = value
                entry["status"] = "documented"
                entry["sources"] = [{"type": "user-provided"}]
            elif route_type in required:
                entry["status"] = "missing"
            else:
                entry["status"] = "not-applicable"

        statuses = {
            profile["routes"][route_type]["status"] for route_type in required
        }
        profile["status"] = (
            "complete"
            if statuses <= {"documented", "verified"}
            else "incomplete"
        )

    catalog["generated_at"] = (
        dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    )


def route_value(
    catalog: dict[str, Any],
    environment: str,
    route_type: str,
) -> str:
    return str(
        catalog.get("environments", {})
        .get(environment, {})
        .get("routes", {})
        .get(route_type, {})
        .get("url", "")
    )


def write_route_catalog(path: Path, catalog: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def quoted(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def yaml_lines(config: dict[str, Any], indent: int = 0) -> list[str]:
    lines: list[str] = []
    prefix = " " * indent
    for key, value in config.items():
        if isinstance(value, dict):
            lines.append(f"{prefix}{key}:")
            lines.extend(yaml_lines(value, indent + 2))
        elif isinstance(value, list):
            if not value:
                lines.append(f"{prefix}{key}: []")
            else:
                lines.append(f"{prefix}{key}:")
                for item in value:
                    lines.append(f"{prefix}  - {quoted(item)}")
        else:
            lines.append(f"{prefix}{key}: {quoted(value)}")
    return lines


def repository_entry(
    url: str = "",
    branch: str = "main",
    path: str = "",
) -> dict[str, Any]:
    return {
        "url": url,
        "branch": branch,
        "path": path,
        "visibility": "unknown",
        "provider": "",
        "auth_method": "",
        "auth_configured": False,
        "credential_env": "",
        "access_status": "not-checked",
        "clone_status": "not-cloned",
        "clone_path": "",
        "commit": "",
    }


def task_board_config() -> dict[str, Any]:
    return {
        "enabled": False,
        "provider": "",
        "base_url": "",
        "project": "",
        "board": "",
        "scope_type": "",
        "scope_value": "",
        "query": "",
        "include_types": ["epic", "feature", "user-story", "task", "bug"],
        "include_comments": False,
        "include_attachments": False,
        "auth_method": "",
        "auth_configured": False,
        "credential_env": "",
        "access_mode": "read-only",
        "access_status": "not-checked",
        "knowledge_path": "qa-knowledge/work-items.json",
        "write_enabled": False,
    }


def environment_files_config(
    repositories: dict[str, Any],
) -> dict[str, Any]:
    def project_root(name: str) -> str:
        repository = repositories.get(name, {})
        return str(
            repository.get("clone_path")
            or repository.get("path")
            or ""
        )

    return {
        "audit_enabled": True,
        "create_if_missing": True,
        "require_gitignore": True,
        "permissions": "0600",
        "expose_values": False,
        "projects": {
            "frontend": {
                "root": project_root("frontend"),
                "env_file": ".env",
                "template": "",
                "status": "not-checked",
            },
            "backend": {
                "root": project_root("backend"),
                "env_file": ".env",
                "template": "",
                "status": "not-checked",
            },
            "automation": {
                "root": "qa-automation",
                "env_file": ".env",
                "template": "",
                "status": "not-checked",
            },
            "performance": {
                "root": "qa-performance",
                "env_file": ".env",
                "template": "",
                "status": "not-checked",
            },
        },
    }


def gitignore_config(
    repositories: dict[str, Any],
) -> dict[str, Any]:
    def project_root(name: str) -> str:
        repository = repositories.get(name, {})
        return str(
            repository.get("clone_path")
            or repository.get("path")
            or ""
        )

    return {
        "audit_enabled": True,
        "apply_project_defaults": True,
        "managed_block": "qa-skill",
        "protect_examples": True,
        "projects": {
            "frontend": {
                "root": project_root("frontend"),
                "status": "not-checked",
            },
            "backend": {
                "root": project_root("backend"),
                "status": "not-checked",
            },
            "automation": {
                "root": "qa-automation",
                "status": "not-checked",
            },
            "performance": {
                "root": "qa-performance",
                "status": "not-checked",
            },
        },
    }


def configure_repository(
    label: str,
    url: str,
    branch: str,
    path: str = "",
) -> dict[str, Any]:
    repository = repository_entry(url, branch, path)
    repository["visibility"] = ask_choice(
        f"Visibilidad del repositorio {label}",
        ["public", "private", "unknown"],
        "private",
    )
    repository["provider"] = ask_text(
        f"Proveedor de {label} (github, gitlab, azure-devops, bitbucket u otro)"
    )
    if repository["visibility"] == "public":
        repository["auth_method"] = "none"
        repository["auth_configured"] = True
        return repository

    repository["auth_configured"] = ask_bool(
        f"¿Este entorno ya está autenticado para {label}?"
    )
    repository["auth_method"] = ask_choice(
        f"Método de autenticación para {label}",
        ["connector", "cli", "ssh", "credential-manager", "environment", "other"],
        "cli",
    )
    if repository["auth_method"] == "environment":
        repository["credential_env"] = ask_text(
            f"Nombre de la variable de entorno para {label}"
        )
    if not repository["auth_configured"]:
        print(
            "Conectar o configurar el método elegido antes de verificar y clonar. "
            "No ingresar secretos en este asistente."
        )
    return repository


def interactive_config(
    project_name: str,
    environment: str,
    route_catalog: dict[str, Any],
    route_catalog_path: Path,
) -> dict[str, Any]:
    source_access = ask_bool("¿Tenés acceso al código fuente?")
    repositories: dict[str, Any] = {
        "layout": "none",
        "frontend": repository_entry(),
        "backend": repository_entry(),
    }
    mode = "black-box"

    if source_access:
        layout = ask_choice(
            "¿Cómo están organizados los repositorios?",
            ["monorepo", "separate"],
            "separate",
        )
        repositories["layout"] = layout
        mode = "hybrid"
        if layout == "monorepo":
            url = ask_text("URL del monorepo")
            branch = ask_text("Rama del monorepo", "main")
            base_repository = configure_repository("monorepo", url, branch)
            repositories["frontend"] = dict(base_repository)
            repositories["frontend"]["path"] = ask_text(
                "Ruta del frontend dentro del repo", "frontend"
            )
            repositories["backend"] = dict(base_repository)
            repositories["backend"]["path"] = ask_text(
                "Ruta del backend dentro del repo", "backend"
            )
        else:
            frontend_url = ask_text("URL del repositorio frontend")
            repositories["frontend"] = configure_repository(
                "frontend",
                frontend_url,
                ask_text("Rama frontend", "main"),
            )
            backend_url = ask_text("URL del repositorio backend")
            repositories["backend"] = configure_repository(
                "backend",
                backend_url,
                ask_text("Rama backend", "main"),
            )

    documentation_sources: list[str] = []
    if ask_bool("¿Tenés documentación funcional o técnica?"):
        raw_sources = ask_text("Enlaces o rutas separados por coma")
        documentation_sources = [
            item.strip() for item in raw_sources.split(",") if item.strip()
        ]

    task_boards = task_board_config()
    if ask_bool("¿Tenés acceso a un tablero de tareas, backlog o user stories?"):
        task_boards["enabled"] = True
        task_boards["provider"] = ask_text(
            "Proveedor del tablero (Jira, Azure DevOps, Linear, GitHub u otro)"
        )
        task_boards["base_url"] = ask_url("URL base del tablero")
        task_boards["project"] = ask_text("Proyecto, organización o espacio")
        task_boards["board"] = ask_text("Nombre o ID del tablero")
        task_boards["scope_type"] = ask_choice(
            "Alcance autorizado",
            ["current-sprint", "sprint", "release", "epic", "filter", "query", "ids"],
            "current-sprint",
        )
        if task_boards["scope_type"] != "current-sprint":
            task_boards["scope_value"] = ask_text(
                "Nombre, ID o valor que identifica el alcance"
            )
        if task_boards["scope_type"] == "query":
            task_boards["query"] = ask_text(
                "Consulta autorizada del tablero, sin credenciales"
            )
        raw_types = ask_text(
            "Tipos de work item separados por coma",
            "epic,feature,user-story,task,bug",
        )
        task_boards["include_types"] = [
            item.strip() for item in raw_types.split(",") if item.strip()
        ]
        task_boards["include_comments"] = ask_bool(
            "¿Está autorizado leer comentarios relevantes?"
        )
        task_boards["include_attachments"] = ask_bool(
            "¿Está autorizado leer adjuntos relevantes?"
        )
        task_boards["auth_configured"] = ask_bool(
            "¿Este entorno ya está autenticado para leer el tablero?"
        )
        task_boards["auth_method"] = ask_choice(
            "Método de autenticación del tablero",
            ["connector", "cli", "oauth", "credential-manager", "environment", "other"],
            "connector",
        )
        if task_boards["auth_method"] == "environment":
            task_boards["credential_env"] = ask_text(
                "Nombre de la variable de entorno con la credencial"
            )
        if not task_boards["auth_configured"]:
            print(
                "Conectar o configurar el método elegido antes de verificar el "
                "tablero. No ingresar tokens ni contraseñas en este asistente."
            )

    allowed_execution_environments = ask_environment_aliases(environment)
    configure_environment_routes(
        route_catalog,
        allowed_execution_environments,
    )
    frontend_url = route_value(route_catalog, environment, "frontend_url")
    api_base_url = route_value(route_catalog, environment, "api_base_url")
    auth_method = ask_text("Método de autenticación, si se conoce")
    test_users = ask_bool("¿Hay usuarios de prueba disponibles?")

    db_access = ask_choice(
        "¿Qué acceso existe a la base?",
        ["read-write", "read-only", "schema-only", "none"],
        "none",
    )
    database: dict[str, Any] = {
        "access_level": db_access,
        "engine": "",
        "host": "",
        "port": None,
        "name": "",
        "authentication": "",
        "read_connection_env": "QA_{ENV}_DB_READ_CONNECTION",
        "write_connection_env": "QA_{ENV}_DB_WRITE_CONNECTION",
        "allow_write": False,
    }
    if db_access != "none":
        database["engine"] = ask_text(
            "Motor de base (sql-server, mongodb, cosmos u otro)"
        )
        database["host"] = ask_text("Servidor o host")
        port = ask_text("Puerto, si aplica")
        database["port"] = int(port) if port.isdigit() else None
        database["name"] = ask_text("Nombre de la base")
        database["authentication"] = ask_text(
            "Autenticación (password, entra, integrated, managed-identity)"
        )
        database["read_connection_env"] = ask_text(
            "Patrón de variable con la conexión de lectura",
            "QA_{ENV}_DB_READ_CONNECTION",
        )
        if db_access == "read-write":
            database["write_connection_env"] = ask_text(
                "Patrón de variable con la conexión de escritura",
                "QA_{ENV}_DB_WRITE_CONNECTION",
            )
            database["allow_write"] = ask_bool(
                "¿Está autorizada la escritura controlada en este ambiente?"
            )

    data_provisioning = {
        "api_available": ask_bool("¿La API permite crear datos de prueba?"),
        "admin_ui_available": ask_bool(
            "¿Existe una interfaz administrativa para preparar datos?"
        ),
        "fixtures_available": ask_bool(
            "¿Existen fixtures, seeds o factories reutilizables?"
        ),
    }

    external_dependencies: dict[str, Any] = {
        "mocking_allowed": False,
        "default_mode": "blocked",
        "bind_host": "127.0.0.1",
        "request_bodies_logged": False,
        "services": [],
    }
    if ask_bool("¿La preparación de datos depende de APIs de terceros?"):
        external_dependencies["mocking_allowed"] = ask_bool(
            "¿Está autorizado usar mocks contractuales en ambientes QA?"
        )
        if external_dependencies["mocking_allowed"]:
            external_dependencies["default_mode"] = "contract-mock"
        while True:
            service_name = ask_text("Nombre de la API o servicio externo")
            if not service_name:
                print("El nombre es obligatorio para registrar la dependencia.")
                continue
            service_token = (
                re.sub(r"[^A-Za-z0-9]", "_", service_name).strip("_").upper()
                or "EXTERNAL_SERVICE"
            )
            service = {
                "name": service_name,
                "contract_source": ask_text(
                    "Ruta o URL del contrato/documentación, si existe"
                ),
                "contract_version": ask_text(
                    "Versión del contrato, si se conoce"
                ),
                "sandbox_available": ask_bool(
                    "¿El proveedor dispone de sandbox?"
                ),
                "base_url_env": f"QA_{{ENV}}_{service_token}_BASE_URL",
                "mock_authorized": (
                    ask_bool(f"¿Autorizar mock contractual para {service_name}?")
                    if external_dependencies["mocking_allowed"]
                    else False
                ),
            }
            external_dependencies["services"].append(service)
            if not ask_bool("¿Agregar otra API de terceros?"):
                break

    provider = ask_text(
        "Gestor de casos/defectos (Jira/Xray, Zephyr, TestRail, Azure DevOps u otro)"
    )
    test_management = {
        "provider": provider,
        "project": ask_text("Proyecto o espacio del gestor") if provider else "",
        "publish_enabled": (
            ask_bool("¿Se permite publicar después de mostrar un preview?")
            if provider
            else False
        ),
    }

    api_tool = ask_choice(
        "Herramienta API",
        ["pytest-httpx", "rest-assured"],
        "pytest-httpx",
    )
    performance_tool = ask_choice(
        "Herramienta performance",
        ["locust", "artillery"],
        "locust",
    )

    return {
        "project": {
            "name": project_name,
            "mode": mode,
            "environment": environment,
        },
        "repositories": repositories,
        "documentation": {"sources": documentation_sources},
        "task_boards": task_boards,
        "application": {
            "frontend_url": frontend_url,
            "api_base_url": api_base_url,
            "auth_method": auth_method,
            "test_users_available": test_users,
        },
        "execution": {
            "default_environment": environment,
            "target_environment_env": "QA_TARGET_ENV",
            "allowed_environments": allowed_execution_environments,
            "allowed_environments_env": "QA_ALLOWED_ENVIRONMENTS",
            "variable_pattern": "QA_{ENV}_{SETTING}",
            "route_catalog_path": str(route_catalog_path),
            "required_route_types": ["frontend_url", "api_base_url"],
            "discover_routes_before_prompting": True,
            "allow_generic_fallback_env": "QA_ALLOW_GENERIC_ENV_FALLBACK",
            "allow_production_env": "QA_ALLOW_PRODUCTION",
        },
        "environment_files": environment_files_config(repositories),
        "gitignore": gitignore_config(repositories),
        "database": database,
        "data_provisioning": data_provisioning,
        "external_dependencies": external_dependencies,
        "data_generation": {
            "formats": ["json", "csv"],
            "csv_mode": "per-entity",
            "csv_encoding": "utf-8",
            "create_inventory": True,
            "inventory_formats": ["json", "csv", "markdown"],
            "show_created_data_summary": True,
            "require_seed_receipt": True,
        },
        "verification_queries": {
            "generate_after_execution": True,
            "execute_automatically": False,
            "require_filter": True,
            "include_count_query": True,
            "include_detail_query": True,
            "output_dir": "qa-artifacts/data/verification",
        },
        "test_management": test_management,
        "test_generation": {
            "coverage_profile": "comprehensive",
            "required_layers": ["frontend", "backend"],
            "required_scenario_families": [
                "happy-path",
                "unhappy-path",
                "boundary",
            ],
            "activate_domain_scenario_families": True,
            "require_business_rule_mapping": True,
            "pairwise_for_large_combinations": True,
            "stop_on_semantic_saturation": True,
            "include_e2e": True,
            "require_explicit_blockers": True,
            "manual_output_format": "spanish-block",
        },
        "tooling": {
            "frontend": "playwright-python",
            "api": api_tool,
            "performance": performance_tool,
        },
        "paths": {
            "knowledge": "qa-knowledge",
            "history": "qa-history",
            "artifacts": "qa-artifacts",
        },
    }


def default_config(
    project_name: str,
    environment: str,
    mode: str,
    allowed_environments: list[str] | None = None,
    route_catalog_path: Path = Path("qa-knowledge/environment-routes.json"),
) -> dict[str, Any]:
    execution_environments = allowed_environments or [environment]
    repositories = {
        "layout": "none",
        "frontend": repository_entry(),
        "backend": repository_entry(),
    }
    return {
        "project": {
            "name": project_name,
            "mode": mode,
            "environment": environment,
        },
        "repositories": repositories,
        "documentation": {"sources": []},
        "task_boards": task_board_config(),
        "application": {
            "frontend_url": "",
            "api_base_url": "",
            "auth_method": "",
            "test_users_available": False,
        },
        "execution": {
            "default_environment": environment,
            "target_environment_env": "QA_TARGET_ENV",
            "allowed_environments": execution_environments,
            "allowed_environments_env": "QA_ALLOWED_ENVIRONMENTS",
            "variable_pattern": "QA_{ENV}_{SETTING}",
            "route_catalog_path": str(route_catalog_path),
            "required_route_types": ["frontend_url", "api_base_url"],
            "discover_routes_before_prompting": True,
            "allow_generic_fallback_env": "QA_ALLOW_GENERIC_ENV_FALLBACK",
            "allow_production_env": "QA_ALLOW_PRODUCTION",
        },
        "environment_files": environment_files_config(repositories),
        "gitignore": gitignore_config(repositories),
        "database": {
            "access_level": "none",
            "engine": "",
            "host": "",
            "port": None,
            "name": "",
            "authentication": "",
            "read_connection_env": "QA_{ENV}_DB_READ_CONNECTION",
            "write_connection_env": "QA_{ENV}_DB_WRITE_CONNECTION",
            "allow_write": False,
        },
        "data_provisioning": {
            "api_available": False,
            "admin_ui_available": False,
            "fixtures_available": False,
        },
        "external_dependencies": {
            "mocking_allowed": False,
            "default_mode": "blocked",
            "bind_host": "127.0.0.1",
            "request_bodies_logged": False,
            "services": [],
        },
        "data_generation": {
            "formats": ["json", "csv"],
            "csv_mode": "per-entity",
            "csv_encoding": "utf-8",
            "create_inventory": True,
            "inventory_formats": ["json", "csv", "markdown"],
            "show_created_data_summary": True,
            "require_seed_receipt": True,
        },
        "verification_queries": {
            "generate_after_execution": True,
            "execute_automatically": False,
            "require_filter": True,
            "include_count_query": True,
            "include_detail_query": True,
            "output_dir": "qa-artifacts/data/verification",
        },
        "test_management": {
            "provider": "",
            "project": "",
            "publish_enabled": False,
        },
        "test_generation": {
            "coverage_profile": "comprehensive",
            "required_layers": ["frontend", "backend"],
            "required_scenario_families": [
                "happy-path",
                "unhappy-path",
                "boundary",
            ],
            "activate_domain_scenario_families": True,
            "require_business_rule_mapping": True,
            "pairwise_for_large_combinations": True,
            "stop_on_semantic_saturation": True,
            "include_e2e": True,
            "require_explicit_blockers": True,
            "manual_output_format": "spanish-block",
        },
        "tooling": {
            "frontend": "playwright-python",
            "api": "pytest-httpx",
            "performance": "locust",
        },
        "paths": {
            "knowledge": "qa-knowledge",
            "history": "qa-history",
            "artifacts": "qa-artifacts",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create qa-project.yaml without storing secrets."
    )
    parser.add_argument("--output", default="qa-project.yaml")
    parser.add_argument("--project-name", default="qa-project")
    parser.add_argument("--environment", default="qa")
    parser.add_argument(
        "--allowed-environments",
        help="Aliases separados por coma; incluye automáticamente --environment",
    )
    parser.add_argument(
        "--route-catalog",
        type=Path,
        default=Path("qa-knowledge/environment-routes.json"),
        help="Catálogo que se revisa antes de preguntar rutas faltantes",
    )
    parser.add_argument(
        "--mode",
        choices=["white-box", "black-box", "hybrid"],
        default="black-box",
    )
    parser.add_argument("--non-interactive", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    output = Path(args.output)
    if output.exists() and not args.force:
        parser.error(f"{output} already exists; use --force to replace it")

    try:
        environment = parse_environment_aliases("", args.environment)[0]
        allowed_environments = parse_environment_aliases(
            args.allowed_environments or "",
            environment,
        )
    except ValueError as exc:
        parser.error(str(exc))

    try:
        route_catalog = load_route_catalog(args.route_catalog)
        ensure_route_profiles(route_catalog, allowed_environments)
    except ValueError as exc:
        parser.error(str(exc))

    if args.non_interactive:
        config = default_config(
            args.project_name,
            environment,
            args.mode,
            allowed_environments,
            args.route_catalog,
        )
    else:
        project_name = ask_text("Nombre del proyecto", args.project_name)
        while True:
            candidate = ask_text("Ambiente objetivo", environment)
            try:
                environment = parse_environment_aliases("", candidate)[0]
                break
            except ValueError as exc:
                print(exc)
        config = interactive_config(
            project_name,
            environment,
            route_catalog,
            args.route_catalog,
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(yaml_lines(config)) + "\n", encoding="utf-8")
    route_catalog["generated_at"] = (
        dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    )
    write_route_catalog(args.route_catalog, route_catalog)
    print(f"Created {output}")
    print(f"Updated {args.route_catalog}")
    print("No secret values were stored.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
