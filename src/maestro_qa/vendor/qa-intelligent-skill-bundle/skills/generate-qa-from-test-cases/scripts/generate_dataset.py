#!/usr/bin/env python3
"""Generate deterministic relational or document QA datasets from JSON specs."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import random
import re
import string
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

from data_inventory import build_inventory, write_inventory_files


IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class DatasetError(ValueError):
    pass


def load_spec(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise DatasetError("Dataset spec must be a JSON object")
    if not isinstance(data.get("entities"), list) or not data["entities"]:
        raise DatasetError("'entities' must be a non-empty list")
    return data


def deterministic_uuid(token: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, token))


def random_text(rng: random.Random, length: int) -> str:
    alphabet = string.ascii_lowercase + string.digits
    return "".join(rng.choice(alphabet) for _ in range(max(length, 1)))


def resolve_ref(
    rule: dict[str, Any],
    generated: dict[str, list[dict[str, Any]]],
    row_index: int,
) -> Any:
    entity_name = rule.get("entity")
    field = rule.get("field")
    if not isinstance(entity_name, str) or not isinstance(field, str):
        raise DatasetError("ref requires string 'entity' and 'field'")
    rows = generated.get(entity_name)
    if not rows:
        raise DatasetError(
            f"ref points to unavailable entity '{entity_name}'; order dependencies first"
        )
    reference_index = row_index % len(rows)
    if field not in rows[reference_index]:
        raise DatasetError(f"ref field '{entity_name}.{field}' does not exist")
    return rows[reference_index][field]


def generate_value(
    rule: dict[str, Any],
    *,
    rng: random.Random,
    dataset_id: str,
    run_id: str,
    entity_name: str,
    field_name: str,
    row_index: int,
    generated: dict[str, list[dict[str, Any]]],
) -> Any:
    value_type = rule.get("type")
    token = f"{dataset_id}:{entity_name}:{row_index}:{field_name}"

    if value_type == "literal":
        return rule.get("value")
    if value_type == "run_id":
        return run_id
    if value_type == "uuid":
        return deterministic_uuid(token)
    if value_type == "integer":
        minimum = int(rule.get("min", 0))
        maximum = int(rule.get("max", 1000))
        if minimum > maximum:
            raise DatasetError(f"{entity_name}.{field_name}: min exceeds max")
        return rng.randint(minimum, maximum)
    if value_type == "decimal":
        minimum = Decimal(str(rule.get("min", "0")))
        maximum = Decimal(str(rule.get("max", "100")))
        scale = int(rule.get("scale", 2))
        if minimum > maximum:
            raise DatasetError(f"{entity_name}.{field_name}: min exceeds max")
        raw = minimum + (maximum - minimum) * Decimal(str(rng.random()))
        return float(raw.quantize(Decimal(1).scaleb(-scale)))
    if value_type == "boolean":
        return bool(rng.getrandbits(1))
    if value_type == "choice":
        values = rule.get("values")
        if not isinstance(values, list) or not values:
            raise DatasetError(f"{entity_name}.{field_name}: choice needs values")
        return values[row_index % len(values)]
    if value_type == "string":
        prefix = str(rule.get("prefix", "qa"))
        length = int(rule.get("length", 12))
        return f"{prefix}-{random_text(rng, length)}-{row_index + 1}"
    if value_type == "username":
        prefix = str(rule.get("prefix", "qa"))
        return f"{prefix}_{random_text(rng, 8)}_{row_index + 1}"
    if value_type == "email":
        domain = str(rule.get("domain", "example.test"))
        local = random_text(rng, 10)
        return f"qa.{local}.{row_index + 1}@{domain}"
    if value_type in {"date", "datetime"}:
        raw_base = str(rule.get("base", "2030-01-01T00:00:00+00:00"))
        try:
            base = dt.datetime.fromisoformat(raw_base.replace("Z", "+00:00"))
        except ValueError as exc:
            raise DatasetError(
                f"{entity_name}.{field_name}: invalid ISO base datetime"
            ) from exc
        value = base + dt.timedelta(days=row_index)
        return value.date().isoformat() if value_type == "date" else value.isoformat()
    if value_type == "ref":
        return resolve_ref(rule, generated, row_index)

    raise DatasetError(
        f"{entity_name}.{field_name}: unsupported field type '{value_type}'"
    )


def generate(spec: dict[str, Any]) -> dict[str, Any]:
    dataset_id = str(spec.get("dataset_id") or "DS-UNSPECIFIED")
    run_id = str(spec.get("run_id") or f"RUN-{dataset_id}")
    seed = int(spec.get("seed", 0))
    rng = random.Random(seed)
    generated_rows: dict[str, list[dict[str, Any]]] = {}
    output_entities: list[dict[str, Any]] = []

    seen_names: set[str] = set()
    for raw_entity in spec["entities"]:
        if not isinstance(raw_entity, dict):
            raise DatasetError("Every entity must be an object")
        name = raw_entity.get("name")
        if not isinstance(name, str) or not IDENTIFIER.fullmatch(name):
            raise DatasetError(f"Invalid entity name: {name!r}")
        if name in seen_names:
            raise DatasetError(f"Duplicate entity name: {name}")
        seen_names.add(name)

        count = int(raw_entity.get("count", 1))
        if count < 1 or count > 100000:
            raise DatasetError(f"{name}: count must be between 1 and 100000")
        fields = raw_entity.get("fields")
        if not isinstance(fields, dict) or not fields:
            raise DatasetError(f"{name}: fields must be a non-empty object")

        rows: list[dict[str, Any]] = []
        for row_index in range(count):
            row: dict[str, Any] = {}
            for field_name, raw_rule in fields.items():
                if not isinstance(field_name, str) or not IDENTIFIER.fullmatch(
                    field_name
                ):
                    raise DatasetError(f"{name}: invalid field name {field_name!r}")
                if not isinstance(raw_rule, dict):
                    raise DatasetError(f"{name}.{field_name}: rule must be an object")
                row[field_name] = generate_value(
                    raw_rule,
                    rng=rng,
                    dataset_id=dataset_id,
                    run_id=run_id,
                    entity_name=name,
                    field_name=field_name,
                    row_index=row_index,
                    generated=generated_rows,
                )
            rows.append(row)

        generated_rows[name] = rows
        output_entities.append(
            {
                "name": name,
                "target": raw_entity.get("target"),
                "collection": raw_entity.get("collection"),
                "run_id_field": raw_entity.get("run_id_field", "qa_run_id"),
                "identifier_fields": raw_entity.get("identifier_fields", []),
                "display_fields": raw_entity.get("display_fields", []),
                "sensitive_fields": raw_entity.get("sensitive_fields", []),
                "rows": rows,
            }
        )

    return {
        "dataset_id": dataset_id,
        "run_id": run_id,
        "seed": seed,
        "entities": output_entities,
    }


def quote_identifier(identifier: str) -> str:
    parts = identifier.split(".")
    if not 1 <= len(parts) <= 2 or not all(IDENTIFIER.fullmatch(p) for p in parts):
        raise DatasetError(f"Unsafe SQL identifier: {identifier!r}")
    return ".".join(f"[{part}]" for part in parts)


def sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    escaped = str(value).replace("'", "''")
    return f"N'{escaped}'"


def render_sql_preview(dataset: dict[str, Any]) -> str:
    lines = [
        "-- PREVIEW ONLY. Generated for review; do not execute blindly.",
        "SET XACT_ABORT ON;",
        "BEGIN TRANSACTION;",
    ]
    for entity in dataset["entities"]:
        target = entity.get("target")
        if not target:
            continue
        table = quote_identifier(str(target))
        for row in entity["rows"]:
            columns = ", ".join(quote_identifier(column) for column in row)
            values = ", ".join(sql_literal(value) for value in row.values())
            lines.append(f"INSERT INTO {table} ({columns}) VALUES ({values});")
    lines.extend(
        [
            "-- Intentionally roll back this preview.",
            "ROLLBACK TRANSACTION;",
            "",
        ]
    )
    return "\n".join(lines)


def csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return value


def csv_columns(rows: list[dict[str, Any]]) -> list[str]:
    columns: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for column in row:
            if column not in seen:
                columns.append(column)
                seen.add(column)
    return columns


def write_csv_exports(dataset: dict[str, Any], csv_dir: Path) -> list[Path]:
    csv_dir.mkdir(parents=True, exist_ok=True)
    exported: list[Path] = []
    manifest_rows: list[dict[str, Any]] = []

    for entity in dataset["entities"]:
        name = str(entity["name"])
        if not IDENTIFIER.fullmatch(name):
            raise DatasetError(f"Invalid entity name for CSV: {name!r}")
        rows = entity["rows"]
        columns = csv_columns(rows)
        if not columns:
            raise DatasetError(f"{name}: cannot export CSV without columns")

        csv_path = csv_dir / f"{name}.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=columns,
                extrasaction="raise",
                lineterminator="\n",
            )
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        column: csv_value(row.get(column))
                        for column in columns
                    }
                )
        exported.append(csv_path)
        manifest_rows.append(
            {
                "dataset_id": dataset["dataset_id"],
                "run_id": dataset["run_id"],
                "entity": name,
                "file": csv_path.name,
                "target": entity.get("target") or "",
                "collection": entity.get("collection") or "",
                "row_count": len(rows),
                "status": "GENERATED_NOT_INSERTED",
                "identifier_fields": json.dumps(
                    entity.get("identifier_fields", []),
                    separators=(",", ":"),
                ),
                "display_fields": json.dumps(
                    entity.get("display_fields", []),
                    separators=(",", ":"),
                ),
            }
        )

    manifest_path = csv_dir / "manifest.csv"
    manifest_columns = [
        "dataset_id",
        "run_id",
        "entity",
        "file",
        "target",
        "collection",
        "row_count",
        "status",
        "identifier_fields",
        "display_fields",
    ]
    with manifest_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=manifest_columns,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(manifest_rows)
    exported.append(manifest_path)
    return exported


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--csv-dir",
        type=Path,
        help="CSV output directory; defaults to <json-output-stem>-csv.",
    )
    parser.add_argument("--sql-preview", type=Path)
    parser.add_argument(
        "--inventory-json",
        type=Path,
        help="Sanitized inventory JSON; defaults beside the canonical dataset.",
    )
    parser.add_argument(
        "--inventory-csv",
        type=Path,
        help="Entity and target inventory CSV.",
    )
    parser.add_argument(
        "--inventory-markdown",
        type=Path,
        help="Human-readable table/collection inventory.",
    )
    args = parser.parse_args()

    try:
        spec = load_spec(args.spec)
        dataset = generate(spec)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(dataset, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        csv_dir = args.csv_dir or (
            args.output.parent / f"{args.output.stem}-csv"
        )
        csv_files = write_csv_exports(dataset, csv_dir)
        if args.sql_preview:
            args.sql_preview.parent.mkdir(parents=True, exist_ok=True)
            args.sql_preview.write_text(
                render_sql_preview(dataset),
                encoding="utf-8",
            )
        inventory = build_inventory(
            dataset,
            status="GENERATED_NOT_INSERTED",
            operation="generate-dataset",
        )
        inventory_json = args.inventory_json or (
            args.output.parent / f"{args.output.stem}-inventory.json"
        )
        inventory_csv = args.inventory_csv or (
            args.output.parent / f"{args.output.stem}-inventory.csv"
        )
        inventory_markdown = args.inventory_markdown or (
            args.output.parent / f"{args.output.stem}-inventory.md"
        )
        write_inventory_files(
            inventory,
            json_path=inventory_json,
            csv_path=inventory_csv,
            markdown_path=inventory_markdown,
        )
    except (OSError, json.JSONDecodeError, DatasetError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 1

    row_count = sum(len(entity["rows"]) for entity in dataset["entities"])
    print(
        json.dumps(
            {
                "dataset_id": dataset["dataset_id"],
                "run_id": dataset["run_id"],
                "status": "GENERATED_NOT_INSERTED",
                "entities": len(dataset["entities"]),
                "rows": row_count,
                "output": str(args.output),
                "csv_dir": str(csv_dir),
                "csv_files": [str(path) for path in csv_files],
                "inventory_json": str(inventory_json),
                "inventory_csv": str(inventory_csv),
                "inventory_markdown": str(inventory_markdown),
                "targets": [
                    {
                        "entity": entity["entity"],
                        "target_type": entity["target_type"],
                        "target": entity["target"],
                        "rows": entity["planned_row_count"],
                        "records": entity["records"],
                    }
                    for entity in inventory["entities"]
                ],
                "sql_preview": str(args.sql_preview) if args.sql_preview else None,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
