#!/usr/bin/env python3
"""Render canonical QA cases as readable Spanish manual test cases."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


STATUS_LABELS = {
    "NOT_EXECUTED": "No ejecutado",
    "PASSED": "Pass",
    "FAILED": "Fail",
    "BLOCKED": "Blocked",
    "SKIPPED": "Skipped",
}
LAYER_LABELS = {
    "frontend": "Frontend",
    "backend": "Backend",
    "e2e": "End-to-end",
    "data": "Datos",
    "performance": "Performance",
}


def load_cases(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        cases = data
    elif isinstance(data, dict) and isinstance(data.get("cases"), list):
        cases = data["cases"]
    else:
        raise ValueError("Expected a JSON list or an object with a 'cases' list")
    if not all(isinstance(case, dict) for case in cases):
        raise ValueError("Every case must be a JSON object")
    return cases


def render_preconditions(values: Any) -> list[str]:
    if not isinstance(values, list) or not values:
        return ["Precondiciones: Ninguna"]
    if len(values) == 1:
        return [f"Precondiciones: {values[0]}"]
    lines = ["Precondiciones:"]
    lines.extend(f"- {value}" for value in values)
    return lines


def render_steps(values: Any) -> list[str]:
    lines = ["Pasos:"]
    if not isinstance(values, list) or not values:
        lines.append("1. [Pendiente de definición]")
        return lines
    ordered = sorted(
        values,
        key=lambda step: step.get("order", 0) if isinstance(step, dict) else 0,
    )
    for index, step in enumerate(ordered, start=1):
        if isinstance(step, dict):
            action = step.get("action") or "[Pendiente de definición]"
        else:
            action = str(step)
        lines.append(f"{index}. {action}")
    return lines


def render_optional_list(label: str, values: Any) -> list[str]:
    if not isinstance(values, list) or not values:
        return []
    return [f"{label}: {', '.join(str(value) for value in values)}"]


def render_case(case: dict[str, Any], index: int) -> str:
    status = STATUS_LABELS.get(
        str(case.get("status", "NOT_EXECUTED")),
        str(case.get("status", "No ejecutado")),
    )
    actual_result = case.get("actual_result") or "Pendiente"
    layer = LAYER_LABELS.get(
        str(case.get("layer", "")),
        str(case.get("layer", "Sin definir")),
    )

    lines = [
        f"[CASO DE PRUEBA {index:02d}]",
        f"ID: {case.get('case_id', '[Sin ID]')}",
        f"Capa: {layer}",
        f"Feature ID: {case.get('feature_id', '[Sin feature_id]')}",
        f"Familia: {case.get('scenario_family', '[Sin scenario_family]')}",
        f"Título: {case.get('title', '[Sin título]')}",
    ]
    lines.extend(render_preconditions(case.get("preconditions")))
    lines.extend(render_steps(case.get("steps")))
    lines.extend(
        [
            f"Resultado Esperado: {case.get('expected_result', '[Pendiente]')}",
            f"Resultado Real: {actual_result}",
            f"Estado: {status}",
        ]
    )

    contract = case.get("data_contract")
    if isinstance(contract, dict) and contract.get("dataset_id"):
        lines.append(f"Dataset: {contract['dataset_id']}")
    lines.extend(render_optional_list("Evidencia requerida", case.get("evidence_required")))
    lines.extend(render_optional_list("Historia/Tarea", case.get("work_item_ids")))
    lines.extend(render_optional_list("Reglas de negocio", case.get("business_rule_ids")))
    lines.extend(render_optional_list("Dimensiones", case.get("coverage_dimensions")))
    lines.extend(render_optional_list("Fuentes", case.get("sources")))
    lines.append("-" * 50)
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--layer",
        choices=sorted(LAYER_LABELS),
        help="Render only one test layer.",
    )
    args = parser.parse_args()

    try:
        cases = load_cases(args.input)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"rendered": False, "error": str(exc)}, ensure_ascii=False))
        return 2

    if args.layer:
        cases = [case for case in cases if case.get("layer") == args.layer]

    rendered = "\n\n".join(
        render_case(case, index)
        for index, case in enumerate(cases, start=1)
    )
    if rendered:
        rendered += "\n"

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        print(
            json.dumps(
                {
                    "rendered": True,
                    "case_count": len(cases),
                    "output": str(args.output),
                    "layer": args.layer or "all",
                },
                ensure_ascii=False,
            )
        )
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
