#!/usr/bin/env python3
"""Safely introspect and provision QA data in SQL Server or MongoDB."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any, Iterable

from data_inventory import build_inventory, write_json as write_inventory_json

from env_file_manager import (
    EnvFileError,
    git_ignores,
    is_placeholder,
    load_env_values,
)


SAFE_ENVIRONMENTS = {"dev", "development", "test", "qa", "staging"}
DEFAULT_EXECUTION_ENVIRONMENTS = SAFE_ENVIRONMENTS | {"main"}
PRODUCTION_ENVIRONMENTS = {"prod", "production"}
ENVIRONMENT_ALIAS = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
TRUTHY = {"1", "true", "yes", "y", "si", "sí"}


class DbToolError(RuntimeError):
    pass


def json_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if value is None or is_placeholder(value):
        raise DbToolError(f"Required environment variable '{name}' is not set")
    return value


def is_truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in TRUTHY


def normalize_environment(value: str) -> str:
    environment = value.strip().lower()
    if not ENVIRONMENT_ALIAS.fullmatch(environment):
        raise DbToolError(
            f"Invalid QA environment alias {value!r}; "
            "use letters, numbers, '-' or '_'."
        )
    return environment


def parse_environment_list(variable: str, defaults: set[str]) -> set[str]:
    raw = os.environ.get(variable, "")
    if not raw.strip():
        return set(defaults)
    environments = {
        normalize_environment(value)
        for value in raw.split(",")
        if value.strip()
    }
    if not environments:
        raise DbToolError(f"{variable} cannot be empty")
    prefixes: dict[str, str] = {}
    for environment in environments:
        token = environment_token(environment)
        if token in prefixes and prefixes[token] != environment:
            raise DbToolError(
                f"Environments {prefixes[token]!r} and {environment!r} "
                f"both resolve to QA_{token}_ variables"
            )
        prefixes[token] = environment
    return environments


def select_environment(argument: str | None) -> str:
    environment = normalize_environment(
        argument
        or os.environ.get("QA_TARGET_ENV")
        or os.environ.get("QA_DEFAULT_ENV")
        or "qa"
    )
    allowed = parse_environment_list(
        "QA_ALLOWED_ENVIRONMENTS",
        DEFAULT_EXECUTION_ENVIRONMENTS,
    )
    if environment not in allowed:
        raise DbToolError(
            f"Environment {environment!r} is not in QA_ALLOWED_ENVIRONMENTS"
        )
    if environment in PRODUCTION_ENVIRONMENTS and not is_truthy(
        os.environ.get("QA_ALLOW_PRODUCTION")
    ):
        raise DbToolError(
            f"Environment {environment!r} requires QA_ALLOW_PRODUCTION=true"
        )
    return environment


def environment_token(environment: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "_", environment).upper()


def resolve_connection_env(
    environment: str,
    requested: str | None,
    *,
    write: bool,
) -> str:
    if requested:
        return requested
    suffix = "DB_WRITE_CONNECTION" if write else "DB_READ_CONNECTION"
    scoped_name = f"QA_{environment_token(environment)}_{suffix}"
    if os.environ.get(scoped_name):
        return scoped_name
    generic_name = f"QA_{suffix}"
    if is_truthy(os.environ.get("QA_ALLOW_GENERIC_ENV_FALLBACK")) and os.environ.get(
        generic_name
    ):
        return generic_name
    return scoped_name


def prepare_environment(args: argparse.Namespace) -> None:
    args.environment = select_environment(getattr(args, "environment", None))
    args.connection_env = resolve_connection_env(
        args.environment,
        getattr(args, "connection_env", None),
        write=args.command in {
            "seed-mssql",
            "cleanup-mssql",
            "seed-mongodb",
            "cleanup-mongodb",
        },
    )


def ensure_write_allowed(args: argparse.Namespace) -> None:
    environment = args.environment
    allowed_write_environments = parse_environment_list(
        "QA_ALLOWED_DB_WRITE_ENVIRONMENTS",
        SAFE_ENVIRONMENTS,
    )
    if environment not in allowed_write_environments:
        raise DbToolError(
            f"Environment '{args.environment}' is not write-enabled; "
            "add it explicitly to QA_ALLOWED_DB_WRITE_ENVIRONMENTS"
        )
    if not args.execute:
        raise DbToolError("Execution requires --execute")
    if not args.allow_write:
        raise DbToolError("Execution requires --allow-write")
    if not is_truthy(os.environ.get("QA_ALLOW_DB_WRITE")):
        raise DbToolError("Execution requires QA_ALLOW_DB_WRITE=true")


def quote_identifier(identifier: str) -> str:
    parts = identifier.split(".")
    if not 1 <= len(parts) <= 2 or not all(IDENTIFIER.fullmatch(p) for p in parts):
        raise DbToolError(f"Unsafe SQL identifier: {identifier!r}")
    return ".".join(f"[{part}]" for part in parts)


def load_dataset(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DbToolError(f"Unable to load dataset: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("entities"), list):
        raise DbToolError("Dataset must be an object with an entities list")
    if not isinstance(data.get("run_id"), str) or not data["run_id"].strip():
        raise DbToolError("Dataset requires a non-empty run_id")
    return data


def rows_as_dicts(cursor: Any, rows: Iterable[Any]) -> list[dict[str, Any]]:
    columns = [description[0] for description in cursor.description]
    return [dict(zip(columns, row)) for row in rows]


def connect_mssql(connection_string: str) -> Any:
    try:
        import mssql_python  # type: ignore
    except ImportError as exc:
        raise DbToolError(
            "mssql-python is required. Install it in an isolated Python environment."
        ) from exc
    return mssql_python.connect(connection_string)


def introspect_mssql(args: argparse.Namespace) -> dict[str, Any]:
    connection_string = require_env(args.connection_env)
    connection = connect_mssql(connection_string)
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT
              TABLE_SCHEMA AS table_schema,
              TABLE_NAME AS table_name,
              COLUMN_NAME AS column_name,
              ORDINAL_POSITION AS ordinal_position,
              DATA_TYPE AS data_type,
              IS_NULLABLE AS is_nullable,
              CHARACTER_MAXIMUM_LENGTH AS character_maximum_length,
              NUMERIC_PRECISION AS numeric_precision,
              NUMERIC_SCALE AS numeric_scale
            FROM INFORMATION_SCHEMA.COLUMNS
            ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION
            """
        )
        columns = rows_as_dicts(cursor, cursor.fetchall())

        cursor.execute(
            """
            SELECT
              tc.TABLE_SCHEMA AS table_schema,
              tc.TABLE_NAME AS table_name,
              kcu.COLUMN_NAME AS column_name,
              kcu.ORDINAL_POSITION AS ordinal_position,
              tc.CONSTRAINT_NAME AS constraint_name
            FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
            JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
              ON tc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
             AND tc.TABLE_SCHEMA = kcu.TABLE_SCHEMA
            WHERE tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
            ORDER BY tc.TABLE_SCHEMA, tc.TABLE_NAME, kcu.ORDINAL_POSITION
            """
        )
        primary_keys = rows_as_dicts(cursor, cursor.fetchall())

        cursor.execute(
            """
            SELECT
              OBJECT_SCHEMA_NAME(fkc.parent_object_id) AS parent_schema,
              OBJECT_NAME(fkc.parent_object_id) AS parent_table,
              pc.name AS parent_column,
              OBJECT_SCHEMA_NAME(fkc.referenced_object_id) AS referenced_schema,
              OBJECT_NAME(fkc.referenced_object_id) AS referenced_table,
              rc.name AS referenced_column,
              fk.name AS constraint_name
            FROM sys.foreign_key_columns fkc
            JOIN sys.foreign_keys fk
              ON fk.object_id = fkc.constraint_object_id
            JOIN sys.columns pc
              ON pc.object_id = fkc.parent_object_id
             AND pc.column_id = fkc.parent_column_id
            JOIN sys.columns rc
              ON rc.object_id = fkc.referenced_object_id
             AND rc.column_id = fkc.referenced_column_id
            ORDER BY parent_schema, parent_table, constraint_name
            """
        )
        foreign_keys = rows_as_dicts(cursor, cursor.fetchall())

        cursor.execute("SELECT DB_NAME() AS database_name")
        database_name = cursor.fetchone()[0]
        return {
            "engine": "sql-server",
            "database": database_name,
            "columns": columns,
            "primary_keys": primary_keys,
            "foreign_keys": foreign_keys,
        }
    finally:
        connection.close()


def introspect_mongodb(args: argparse.Namespace) -> dict[str, Any]:
    try:
        from pymongo import MongoClient  # type: ignore
    except ImportError as exc:
        raise DbToolError(
            "pymongo is required. Install it in an isolated Python environment."
        ) from exc

    uri = require_env(args.connection_env)
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    try:
        client.admin.command("ping")
        database = client[args.database]
        collections: list[dict[str, Any]] = []
        for name in sorted(database.list_collection_names()):
            entry: dict[str, Any] = {
                "name": name,
                "indexes": list(database[name].list_indexes()),
            }
            try:
                info = database.command("listCollections", filter={"name": name})
                batches = info.get("cursor", {}).get("firstBatch", [])
                if batches:
                    entry["options"] = batches[0].get("options", {})
            except Exception as exc:  # permissions vary by deployment
                entry["options_error"] = type(exc).__name__
            collections.append(entry)
        return {
            "engine": "mongodb",
            "database": args.database,
            "collections": collections,
        }
    finally:
        client.close()


def sql_seed_plan(dataset: dict[str, Any]) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    for entity in dataset["entities"]:
        target = entity.get("target")
        rows = entity.get("rows")
        if not target:
            continue
        if not isinstance(rows, list) or not rows:
            continue
        keys = list(rows[0])
        if not keys:
            continue
        if any(not isinstance(row, dict) or list(row) != keys for row in rows):
            raise DbToolError(
                f"Entity {entity.get('name')} must have consistent row columns"
            )
        statement = (
            f"INSERT INTO {quote_identifier(str(target))} "
            f"({', '.join(quote_identifier(key) for key in keys)}) "
            f"VALUES ({', '.join('?' for _ in keys)})"
        )
        plan.append(
            {
                "entity": entity.get("name"),
                "target": target,
                "statement": statement,
                "columns": keys,
                "rows": [[row[key] for key in keys] for row in rows],
            }
        )
    return plan


def seed_mssql(args: argparse.Namespace, dataset: dict[str, Any]) -> dict[str, Any]:
    plan = sql_seed_plan(dataset)
    if not args.execute:
        return {
            "dry_run": True,
            "engine": "sql-server",
            "run_id": dataset["run_id"],
            "operations": [
                {
                    "entity": item["entity"],
                    "target": item["target"],
                    "rows": len(item["rows"]),
                    "statement": item["statement"],
                }
                for item in plan
            ],
        }

    ensure_write_allowed(args)
    connection_string = require_env(args.connection_env)
    connection = connect_mssql(connection_string)
    inserted: list[dict[str, Any]] = []
    try:
        cursor = connection.cursor()
        for operation in plan:
            cursor.executemany(operation["statement"], operation["rows"])
            inserted.append(
                {
                    "entity": operation["entity"],
                    "target": operation["target"],
                    "rows": len(operation["rows"]),
                }
            )
        connection.commit()
        return {
            "dry_run": False,
            "engine": "sql-server",
            "run_id": dataset["run_id"],
            "inserted": inserted,
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def cleanup_mssql(args: argparse.Namespace, dataset: dict[str, Any]) -> dict[str, Any]:
    run_id = args.run_id or dataset["run_id"]
    operations: list[dict[str, str]] = []
    for entity in reversed(dataset["entities"]):
        target = entity.get("target")
        run_id_field = entity.get("run_id_field")
        if not target or not run_id_field:
            continue
        statement = (
            f"DELETE FROM {quote_identifier(str(target))} "
            f"WHERE {quote_identifier(str(run_id_field))} = ?"
        )
        operations.append(
            {
                "entity": str(entity.get("name")),
                "target": str(target),
                "statement": statement,
            }
        )

    if not args.execute:
        return {
            "dry_run": True,
            "engine": "sql-server",
            "run_id": run_id,
            "operations": operations,
        }

    ensure_write_allowed(args)
    connection_string = require_env(args.connection_env)
    connection = connect_mssql(connection_string)
    deleted: list[dict[str, Any]] = []
    try:
        cursor = connection.cursor()
        for operation in operations:
            cursor.execute(operation["statement"], (run_id,))
            deleted.append(
                {
                    "entity": operation["entity"],
                    "target": operation["target"],
                    "rows": cursor.rowcount,
                }
            )
        connection.commit()
        return {
            "dry_run": False,
            "engine": "sql-server",
            "run_id": run_id,
            "deleted": deleted,
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def mongo_seed_plan(dataset: dict[str, Any]) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    for entity in dataset["entities"]:
        collection = entity.get("collection")
        rows = entity.get("rows")
        if not collection or not isinstance(rows, list) or not rows:
            continue
        if not isinstance(collection, str) or not IDENTIFIER.fullmatch(collection):
            raise DbToolError(f"Unsafe MongoDB collection: {collection!r}")
        plan.append(
            {
                "entity": entity.get("name"),
                "collection": collection,
                "documents": rows,
            }
        )
    return plan


def seed_mongodb(args: argparse.Namespace, dataset: dict[str, Any]) -> dict[str, Any]:
    plan = mongo_seed_plan(dataset)
    if not args.execute:
        return {
            "dry_run": True,
            "engine": "mongodb",
            "database": args.database,
            "run_id": dataset["run_id"],
            "operations": [
                {
                    "entity": item["entity"],
                    "collection": item["collection"],
                    "documents": len(item["documents"]),
                }
                for item in plan
            ],
        }

    ensure_write_allowed(args)
    try:
        from pymongo import MongoClient  # type: ignore
    except ImportError as exc:
        raise DbToolError(
            "pymongo is required. Install it in an isolated Python environment."
        ) from exc

    uri = require_env(args.connection_env)
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    inserted: list[dict[str, Any]] = []
    try:
        client.admin.command("ping")
        database = client[args.database]
        for operation in plan:
            result = database[operation["collection"]].insert_many(
                operation["documents"],
                ordered=True,
            )
            inserted.append(
                {
                    "entity": operation["entity"],
                    "collection": operation["collection"],
                    "documents": len(result.inserted_ids),
                    "inserted_ids": [str(value) for value in result.inserted_ids],
                }
            )
        return {
            "dry_run": False,
            "engine": "mongodb",
            "database": args.database,
            "run_id": dataset["run_id"],
            "inserted": inserted,
        }
    finally:
        client.close()


def cleanup_mongodb(args: argparse.Namespace, dataset: dict[str, Any]) -> dict[str, Any]:
    run_id = args.run_id or dataset["run_id"]
    operations: list[dict[str, str]] = []
    for entity in reversed(dataset["entities"]):
        collection = entity.get("collection")
        run_id_field = entity.get("run_id_field")
        if not collection or not run_id_field:
            continue
        if not isinstance(collection, str) or not IDENTIFIER.fullmatch(collection):
            raise DbToolError(f"Unsafe MongoDB collection: {collection!r}")
        if not isinstance(run_id_field, str) or not IDENTIFIER.fullmatch(run_id_field):
            raise DbToolError(f"Unsafe MongoDB field: {run_id_field!r}")
        operations.append(
            {
                "entity": str(entity.get("name")),
                "collection": collection,
                "run_id_field": run_id_field,
            }
        )

    if not args.execute:
        return {
            "dry_run": True,
            "engine": "mongodb",
            "database": args.database,
            "run_id": run_id,
            "operations": operations,
        }

    ensure_write_allowed(args)
    try:
        from pymongo import MongoClient  # type: ignore
    except ImportError as exc:
        raise DbToolError(
            "pymongo is required. Install it in an isolated Python environment."
        ) from exc

    uri = require_env(args.connection_env)
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    deleted: list[dict[str, Any]] = []
    try:
        client.admin.command("ping")
        database = client[args.database]
        for operation in operations:
            result = database[operation["collection"]].delete_many(
                {operation["run_id_field"]: run_id}
            )
            deleted.append(
                {
                    "entity": operation["entity"],
                    "collection": operation["collection"],
                    "documents": result.deleted_count,
                }
            )
        return {
            "dry_run": False,
            "engine": "mongodb",
            "database": args.database,
            "run_id": run_id,
            "deleted": deleted,
        }
    finally:
        client.close()


def add_write_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--connection-env",
        help="Defaults to QA_<ENV>_DB_WRITE_CONNECTION",
    )
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument(
        "--environment",
        help="Overrides QA_TARGET_ENV for this operation",
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--allow-write", action="store_true")
    parser.add_argument(
        "--receipt",
        type=Path,
        help="Write a sanitized seed or cleanup receipt as JSON.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(os.environ.get("QA_ENV_FILE", ".env")),
    )
    parser.add_argument("--require-env-file", action="store_true")
    subparsers = parser.add_subparsers(dest="command", required=True)

    mssql_introspect = subparsers.add_parser("introspect-mssql")
    mssql_introspect.add_argument(
        "--connection-env",
        help="Defaults to QA_<ENV>_DB_READ_CONNECTION",
    )
    mssql_introspect.add_argument("--environment")
    mssql_introspect.add_argument("--output", type=Path, required=True)

    mongo_introspect = subparsers.add_parser("introspect-mongodb")
    mongo_introspect.add_argument(
        "--connection-env",
        help="Defaults to QA_<ENV>_DB_READ_CONNECTION",
    )
    mongo_introspect.add_argument("--environment")
    mongo_introspect.add_argument("--database", required=True)
    mongo_introspect.add_argument("--output", type=Path, required=True)

    mssql_seed = subparsers.add_parser("seed-mssql")
    add_write_flags(mssql_seed)

    mssql_cleanup = subparsers.add_parser("cleanup-mssql")
    add_write_flags(mssql_cleanup)
    mssql_cleanup.add_argument("--run-id")

    mongo_seed = subparsers.add_parser("seed-mongodb")
    add_write_flags(mongo_seed)
    mongo_seed.add_argument("--database", required=True)

    mongo_cleanup = subparsers.add_parser("cleanup-mongodb")
    add_write_flags(mongo_cleanup)
    mongo_cleanup.add_argument("--database", required=True)
    mongo_cleanup.add_argument("--run-id")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.env_file.exists():
            mode = args.env_file.stat().st_mode & 0o777
            if mode & 0o077:
                raise DbToolError(
                    f"Environment file {args.env_file} must use permissions 0600"
                )
            if not git_ignores(args.env_file, args.env_file.parent):
                raise DbToolError(
                    f"Environment file {args.env_file} is not ignored by Git"
                )
            try:
                load_env_values(args.env_file)
            except EnvFileError as exc:
                raise DbToolError(str(exc)) from exc
        elif args.require_env_file:
            raise DbToolError(
                f"Required environment file {args.env_file} does not exist"
            )
        prepare_environment(args)
        if args.command == "introspect-mssql":
            result = introspect_mssql(args)
            json_write(args.output, result)
        elif args.command == "introspect-mongodb":
            result = introspect_mongodb(args)
            json_write(args.output, result)
        else:
            dataset = load_dataset(args.dataset)
            if args.command == "seed-mssql":
                result = seed_mssql(args, dataset)
            elif args.command == "cleanup-mssql":
                result = cleanup_mssql(args, dataset)
            elif args.command == "seed-mongodb":
                result = seed_mongodb(args, dataset)
            elif args.command == "cleanup-mongodb":
                result = cleanup_mongodb(args, dataset)
            else:
                raise DbToolError(f"Unsupported command: {args.command}")
            is_seed = args.command.startswith("seed-")
            if result.get("dry_run"):
                inventory_status = (
                    "PLANNED_NOT_INSERTED"
                    if is_seed
                    else "PLANNED_NOT_CLEANED"
                )
            else:
                inventory_status = "INSERTED" if is_seed else "CLEANED"
            inventory = build_inventory(
                dataset,
                status=inventory_status,
                engine=result.get("engine"),
                environment=args.environment,
                operation=args.command,
                operation_result=result,
            )
            result["dataset_id"] = dataset.get("dataset_id")
            result["environment"] = args.environment
            result["data_inventory"] = inventory["entities"]
            if args.receipt:
                receipt = {
                    "operation_result": result,
                    "inventory": inventory,
                }
                write_inventory_json(args.receipt, receipt)
                result["receipt"] = str(args.receipt)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0
    except DbToolError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": type(exc).__name__,
                    "message": str(exc),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
