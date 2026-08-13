#!/usr/bin/env python3
"""Generate filtered, read-only SQL Server and MongoDB verification queries."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any


IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SENSITIVE_FIELD = re.compile(
    r"(?:password|passwd|secret|token|cookie|authorization|credential|connection[_-]?string|api[_-]?key|private[_-]?key|session)",
    re.IGNORECASE,
)


class VerificationError(ValueError):
    pass


def load_dataset(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise VerificationError("Dataset must be a JSON object")
    if not isinstance(raw.get("entities"), list) or not raw["entities"]:
        raise VerificationError("Dataset 'entities' must be a non-empty list")
    return raw


def quote_sql_identifier(identifier: str) -> str:
    parts = identifier.split(".")
    if not 1 <= len(parts) <= 2 or not all(IDENTIFIER.fullmatch(part) for part in parts):
        raise VerificationError(f"Unsafe SQL identifier: {identifier!r}")
    return ".".join(f"[{part}]" for part in parts)


def sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return "N'" + str(value).replace("'", "''") + "'"


def unique_values(rows: list[dict[str, Any]], field: str) -> list[Any]:
    values: list[Any] = []
    seen: set[str] = set()
    for row in rows:
        if field not in row or row[field] is None:
            continue
        value = row[field]
        if isinstance(value, (dict, list)):
            continue
        key = json.dumps(value, ensure_ascii=False, sort_keys=True)
        if key not in seen:
            values.append(value)
            seen.add(key)
    return values


def entity_columns(entity: dict[str, Any]) -> list[str]:
    columns: list[str] = []
    seen: set[str] = set()
    rows = entity.get("rows")
    if not isinstance(rows, list):
        return columns
    for row in rows:
        if not isinstance(row, dict):
            continue
        for field in row:
            if isinstance(field, str) and field not in seen:
                columns.append(field)
                seen.add(field)
    return columns


def safe_columns(entity: dict[str, Any]) -> list[str]:
    explicit = {
        str(field).lower()
        for field in entity.get("sensitive_fields", [])
        if isinstance(field, str)
    }
    return [
        field
        for field in entity_columns(entity)
        if IDENTIFIER.fullmatch(field)
        and field.lower() not in explicit
        and not SENSITIVE_FIELD.search(field)
    ]


def build_filter(
    entity: dict[str, Any],
    dataset_run_id: str,
    *,
    max_identifiers: int,
) -> dict[str, Any]:
    rows = entity.get("rows")
    if not isinstance(rows, list) or not rows or not all(isinstance(row, dict) for row in rows):
        return {"status": "BLOCKED_NO_ROWS", "reason": "entity has no usable rows"}

    run_id_field = entity.get("run_id_field")
    if (
        isinstance(run_id_field, str)
        and IDENTIFIER.fullmatch(run_id_field)
        and dataset_run_id
        and all(row.get(run_id_field) == dataset_run_id for row in rows)
    ):
        return {
            "status": "READY",
            "strategy": "run-id",
            "field": run_id_field,
            "values": [dataset_run_id],
        }

    identifier_fields = entity.get("identifier_fields", [])
    if not isinstance(identifier_fields, list):
        identifier_fields = []
    for field in identifier_fields:
        if not isinstance(field, str) or not IDENTIFIER.fullmatch(field):
            continue
        values = unique_values(rows, field)
        if not values or len(values) != len(rows):
            continue
        if len(values) > max_identifiers:
            return {
                "status": "BLOCKED_IDENTIFIER_LIMIT",
                "reason": (
                    f"{len(values)} identifiers exceed the safe limit {max_identifiers}; "
                    "add a run_id field or raise the reviewed limit"
                ),
            }
        return {
            "status": "READY",
            "strategy": "known-identifiers",
            "field": field,
            "values": values,
        }
    return {
        "status": "BLOCKED_UNSAFE_FILTER",
        "reason": "no run_id or complete safe identifier field is available",
    }


def sql_where(filter_spec: dict[str, Any]) -> str:
    field = quote_sql_identifier(str(filter_spec["field"]))
    values = filter_spec["values"]
    if filter_spec["strategy"] == "run-id":
        return f"{field} = {sql_literal(values[0])}"
    return f"{field} IN ({', '.join(sql_literal(value) for value in values)})"


def mongo_filter(filter_spec: dict[str, Any]) -> dict[str, Any]:
    field = str(filter_spec["field"])
    values = filter_spec["values"]
    if filter_spec["strategy"] == "run-id":
        return {field: values[0]}
    return {field: {"$in": values}}


def render_sql(
    dataset: dict[str, Any],
    *,
    max_identifiers: int,
) -> tuple[str, list[dict[str, Any]]]:
    lines = [
        "-- QA VERIFICATION QUERIES: READ ONLY",
        "-- Generated from the exact dataset used by the test run.",
        "-- Review the selected environment and connection before executing.",
        "SET NOCOUNT ON;",
        "",
    ]
    records: list[dict[str, Any]] = []
    run_id = str(dataset.get("run_id") or "")
    for raw_entity in dataset["entities"]:
        if not isinstance(raw_entity, dict):
            continue
        name = str(raw_entity.get("name") or "unnamed")
        target = raw_entity.get("target")
        if not isinstance(target, str) or not target:
            continue
        record: dict[str, Any] = {
            "engine": "sql-server",
            "entity": name,
            "target": target,
            "status": "GENERATED_NOT_EXECUTED",
        }
        try:
            table = quote_sql_identifier(target)
            filter_spec = build_filter(
                raw_entity,
                run_id,
                max_identifiers=max_identifiers,
            )
            if filter_spec["status"] != "READY":
                record.update(filter_spec)
                lines.extend(
                    [
                        f"-- {name} -> {target}: {filter_spec['status']}",
                        f"-- {filter_spec['reason']}",
                        "",
                    ]
                )
                records.append(record)
                continue
            columns = safe_columns(raw_entity)
            if not columns:
                raise VerificationError(f"{name}: no safe projection columns")
            where = sql_where(filter_spec)
            projection = ", ".join(quote_sql_identifier(column) for column in columns)
            order_field = str(filter_spec["field"])
            lines.extend(
                [
                    f"-- {name} -> {target}; filter={filter_spec['strategy']}",
                    f"SELECT COUNT_BIG(1) AS [qa_row_count] FROM {table} WHERE {where};",
                    f"SELECT {projection} FROM {table} WHERE {where} ORDER BY {quote_sql_identifier(order_field)};",
                    "",
                ]
            )
            record.update(
                {
                    "filter_strategy": filter_spec["strategy"],
                    "filter_field": filter_spec["field"],
                    "filter_value_count": len(filter_spec["values"]),
                    "projected_fields": columns,
                }
            )
        except VerificationError as exc:
            record.update({"status": "BLOCKED_UNSAFE_QUERY", "reason": str(exc)})
            lines.extend([f"-- {name} -> {target}: BLOCKED_UNSAFE_QUERY", f"-- {exc}", ""])
        records.append(record)
    if len(lines) == 5:
        lines.extend(["-- No SQL Server targets were present in the dataset.", ""])
    return "\n".join(lines), records


def render_mongo(
    dataset: dict[str, Any],
    *,
    max_identifiers: int,
) -> tuple[str, list[dict[str, Any]]]:
    lines = [
        "// QA VERIFICATION QUERIES: READ ONLY",
        "// Generated from the exact dataset used by the test run.",
        "// Review the selected environment and connection before executing.",
        "",
    ]
    records: list[dict[str, Any]] = []
    run_id = str(dataset.get("run_id") or "")
    for raw_entity in dataset["entities"]:
        if not isinstance(raw_entity, dict):
            continue
        name = str(raw_entity.get("name") or "unnamed")
        collection = raw_entity.get("collection")
        if not isinstance(collection, str) or not collection:
            continue
        record: dict[str, Any] = {
            "engine": "mongodb",
            "entity": name,
            "target": collection,
            "status": "GENERATED_NOT_EXECUTED",
        }
        filter_spec = build_filter(
            raw_entity,
            run_id,
            max_identifiers=max_identifiers,
        )
        if filter_spec["status"] != "READY":
            record.update(filter_spec)
            lines.extend(
                [
                    f"// {name} -> {collection}: {filter_spec['status']}",
                    f"// {filter_spec['reason']}",
                    "",
                ]
            )
            records.append(record)
            continue
        columns = safe_columns(raw_entity)
        if not columns:
            record.update(
                {
                    "status": "BLOCKED_UNSAFE_QUERY",
                    "reason": "no safe projection fields are available",
                }
            )
            records.append(record)
            continue
        query = json.dumps(mongo_filter(filter_spec), ensure_ascii=False, separators=(",", ":"))
        projection = json.dumps(
            {field: 1 for field in columns},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        collection_literal = json.dumps(collection, ensure_ascii=False)
        sort_spec = json.dumps(
            {str(filter_spec["field"]): 1},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        lines.extend(
            [
                f"// {name} -> {collection}; filter={filter_spec['strategy']}",
                f"db.getCollection({collection_literal}).countDocuments({query});",
                f"db.getCollection({collection_literal}).find({query}, {projection}).sort({sort_spec});",
                "",
            ]
        )
        record.update(
            {
                "filter_strategy": filter_spec["strategy"],
                "filter_field": filter_spec["field"],
                "filter_value_count": len(filter_spec["values"]),
                "projected_fields": columns,
            }
        )
        records.append(record)
    if len(lines) == 4:
        lines.extend(["// No MongoDB collections were present in the dataset.", ""])
    return "\n".join(lines), records


def render_markdown(manifest: dict[str, Any]) -> str:
    lines = [
        "# Consultas de verificación de datos",
        "",
        f"- Run: `{manifest['run_id']}`",
        f"- Dataset: `{manifest['dataset_id']}`",
        "- Estado: `GENERATED_NOT_EXECUTED`",
        "- Seguridad: solo lectura y filtros acotados al run o a identificadores conocidos.",
        "",
        "| Motor | Entidad | Tabla/Colección | Estado | Filtro |",
        "|---|---|---|---|---|",
    ]
    for query in manifest["queries"]:
        filter_text = query.get("filter_strategy") or query.get("reason") or "N/A"
        safe_filter = str(filter_text).replace("|", "\\|")
        lines.append(
            f"| {query['engine']} | {query['entity']} | {query['target']} | "
            f"{query['status']} | {safe_filter} |"
        )
    lines.extend(
        [
            "",
            "Los archivos fueron generados, no ejecutados. Revisar el ambiente y usar credenciales de solo lectura.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--sql-output", type=Path)
    parser.add_argument("--mongo-output", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--max-identifiers", type=int, default=500)
    args = parser.parse_args()

    try:
        dataset = load_dataset(args.dataset)
        if args.max_identifiers < 1:
            raise VerificationError("max-identifiers must be at least 1")
        run_id = str(dataset.get("run_id") or "RUN-UNSPECIFIED")
        safe_run = re.sub(r"[^A-Za-z0-9_.-]+", "_", run_id).strip("._") or "run"
        output_dir = args.output_dir or Path("qa-artifacts/data/verification") / safe_run
        sql_output = args.sql_output or output_dir / "sql-server.sql"
        mongo_output = args.mongo_output or output_dir / "mongodb.js"
        manifest_path = args.manifest or output_dir / "manifest.json"
        markdown_path = args.markdown or output_dir / "README.md"

        sql_text, sql_records = render_sql(dataset, max_identifiers=args.max_identifiers)
        mongo_text, mongo_records = render_mongo(
            dataset,
            max_identifiers=args.max_identifiers,
        )
        manifest = {
            "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "status": "GENERATED_NOT_EXECUTED",
            "run_id": run_id,
            "dataset_id": str(dataset.get("dataset_id") or "DS-UNSPECIFIED"),
            "source_dataset": str(args.dataset),
            "safety": {
                "read_only": True,
                "filter_required": True,
                "sensitive_fields_projected": False,
                "connection_values_included": False,
            },
            "artifacts": {
                "sql_server": str(sql_output),
                "mongodb": str(mongo_output),
                "markdown": str(markdown_path),
            },
            "queries": sql_records + mongo_records,
        }
        for path in {sql_output, mongo_output, manifest_path, markdown_path}:
            path.parent.mkdir(parents=True, exist_ok=True)
        sql_output.write_text(sql_text, encoding="utf-8")
        mongo_output.write_text(mongo_text, encoding="utf-8")
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        markdown_path.write_text(render_markdown(manifest), encoding="utf-8")
    except (OSError, json.JSONDecodeError, VerificationError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 1

    print(
        json.dumps(
            {
                "status": manifest["status"],
                "run_id": manifest["run_id"],
                "dataset_id": manifest["dataset_id"],
                "query_targets": len(manifest["queries"]),
                "sql_output": str(sql_output),
                "mongo_output": str(mongo_output),
                "manifest": str(manifest_path),
                "markdown": str(markdown_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
