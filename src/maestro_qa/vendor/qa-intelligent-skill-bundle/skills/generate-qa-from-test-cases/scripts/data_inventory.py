#!/usr/bin/env python3
"""Build sanitized QA data inventories from canonical dataset JSON files."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any


SENSITIVE_FIELD = re.compile(
    r"password|passwd|passphrase|secret|token|cookie|authorization|credential|"
    r"connection|api[_-]?key|private[_-]?key|access[_-]?key",
    re.IGNORECASE,
)
ID_FIELD = re.compile(r"(^id$|_id$|^id_|uuid|(^|_)key$)", re.IGNORECASE)


class InventoryError(ValueError):
    pass


def load_dataset(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("entities"), list):
        raise InventoryError("Dataset must be an object with an entities list")
    return data


def string_list(value: Any, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise InventoryError(f"{field} must be a list of non-empty strings")
    return list(dict.fromkeys(item.strip() for item in value))


def operation_counts(result: dict[str, Any] | None) -> dict[str, int]:
    counts: dict[str, int] = {}
    if not isinstance(result, dict):
        return counts
    for key in ("inserted", "deleted", "operations"):
        values = result.get(key)
        if not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, dict) or not isinstance(item.get("entity"), str):
                continue
            raw_count = item.get("rows", item.get("documents"))
            if isinstance(raw_count, int):
                counts[item["entity"]] = raw_count
    return counts


def select_target(entity: dict[str, Any], engine: str | None) -> tuple[str, str]:
    table = entity.get("target")
    collection = entity.get("collection")
    if engine == "mongodb" and collection:
        return "collection", str(collection)
    if engine == "sql-server" and table:
        return "table", str(table)
    if table:
        return "table", str(table)
    if collection:
        return "collection", str(collection)
    return "unspecified", ""


def visible_fields(entity: dict[str, Any], rows: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    identifier_fields = string_list(
        entity.get("identifier_fields"),
        f"{entity.get('name')}.identifier_fields",
    )
    display_fields = string_list(
        entity.get("display_fields"),
        f"{entity.get('name')}.display_fields",
    )
    sensitive_fields = set(
        string_list(
            entity.get("sensitive_fields"),
            f"{entity.get('name')}.sensitive_fields",
        )
    )
    if not identifier_fields and rows:
        identifier_fields = [
            field
            for field in rows[0]
            if ID_FIELD.search(field) and not SENSITIVE_FIELD.search(field)
        ]
    identifier_fields = [
        field
        for field in identifier_fields
        if field not in sensitive_fields and not SENSITIVE_FIELD.search(field)
    ]
    display_fields = [
        field
        for field in display_fields
        if field not in sensitive_fields and not SENSITIVE_FIELD.search(field)
    ]
    return identifier_fields, display_fields


def build_inventory(
    dataset: dict[str, Any],
    *,
    status: str,
    engine: str | None = None,
    environment: str | None = None,
    operation: str | None = None,
    operation_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    affected_counts = (
        operation_counts(operation_result)
        if status in {"INSERTED", "CLEANED"}
        else {}
    )
    entities: list[dict[str, Any]] = []
    for raw_entity in dataset.get("entities", []):
        if not isinstance(raw_entity, dict):
            raise InventoryError("Every dataset entity must be an object")
        entity_name = str(raw_entity.get("name") or "")
        raw_rows = raw_entity.get("rows", [])
        if not isinstance(raw_rows, list) or not all(
            isinstance(row, dict) for row in raw_rows
        ):
            raise InventoryError(f"{entity_name}: rows must be a list of objects")
        rows: list[dict[str, Any]] = raw_rows
        identifier_fields, display_fields = visible_fields(raw_entity, rows)
        record_fields = list(dict.fromkeys(identifier_fields + display_fields))
        records = [
            {field: row.get(field) for field in record_fields if field in row}
            for row in rows
        ]
        target_type, target = select_target(raw_entity, engine)
        entities.append(
            {
                "entity": entity_name,
                "target_type": target_type,
                "target": target,
                "planned_row_count": len(rows),
                "affected_row_count": affected_counts.get(entity_name),
                "identifier_fields": identifier_fields,
                "display_fields": display_fields,
                "records": records,
            }
        )
    return {
        "dataset_id": dataset.get("dataset_id"),
        "run_id": dataset.get("run_id"),
        "status": status,
        "engine": engine,
        "environment": environment,
        "operation": operation,
        "entities": entities,
    }


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def write_csv(path: Path, inventory: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "dataset_id",
        "run_id",
        "status",
        "engine",
        "environment",
        "operation",
        "entity",
        "target_type",
        "target",
        "planned_row_count",
        "affected_row_count",
        "identifier_fields",
        "display_fields",
        "records",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for entity in inventory["entities"]:
            writer.writerow(
                {
                    "dataset_id": inventory.get("dataset_id"),
                    "run_id": inventory.get("run_id"),
                    "status": inventory.get("status"),
                    "engine": inventory.get("engine"),
                    "environment": inventory.get("environment"),
                    "operation": inventory.get("operation"),
                    "entity": entity["entity"],
                    "target_type": entity["target_type"],
                    "target": entity["target"],
                    "planned_row_count": entity["planned_row_count"],
                    "affected_row_count": entity["affected_row_count"],
                    "identifier_fields": json.dumps(entity["identifier_fields"]),
                    "display_fields": json.dumps(entity["display_fields"]),
                    "records": json.dumps(
                        entity["records"],
                        ensure_ascii=False,
                        separators=(",", ":"),
                        default=str,
                    ),
                }
            )


def write_markdown(path: Path, inventory: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Inventario de datos QA",
        "",
        f"- Dataset: `{inventory.get('dataset_id')}`",
        f"- Run: `{inventory.get('run_id')}`",
        f"- Estado: `{inventory.get('status')}`",
        f"- Ambiente: `{inventory.get('environment') or 'sin definir'}`",
        "",
        "| Entidad | Tabla/Colección | Planificados | Afectados | Identificadores y datos visibles |",
        "|---|---|---:|---:|---|",
    ]
    for entity in inventory["entities"]:
        records_preview = entity["records"][:20]
        records = json.dumps(
            records_preview,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        ).replace("|", "\\|")
        if len(entity["records"]) > len(records_preview):
            records += f" … +{len(entity['records']) - len(records_preview)}"
        affected = entity["affected_row_count"]
        lines.append(
            f"| {entity['entity']} | {entity['target']} | "
            f"{entity['planned_row_count']} | "
            f"{affected if affected is not None else '-'} | `{records}` |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_inventory_files(
    inventory: dict[str, Any],
    *,
    json_path: Path,
    csv_path: Path,
    markdown_path: Path,
) -> None:
    write_json(json_path, inventory)
    write_csv(csv_path, inventory)
    write_markdown(markdown_path, inventory)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--status", default="GENERATED_NOT_INSERTED")
    parser.add_argument("--engine", choices=["sql-server", "mongodb"])
    parser.add_argument("--environment")
    parser.add_argument("--operation")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    args = parser.parse_args()
    try:
        dataset = load_dataset(args.dataset)
        inventory = build_inventory(
            dataset,
            status=args.status,
            engine=args.engine,
            environment=args.environment,
            operation=args.operation,
        )
        write_inventory_files(
            inventory,
            json_path=args.output,
            csv_path=args.csv,
            markdown_path=args.markdown,
        )
    except (OSError, json.JSONDecodeError, InventoryError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(inventory, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
