#!/usr/bin/env python3
"""Validate canonical QA test cases, layers, rules, and scenario coverage."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Optional


REQUIRED_FIELDS = {
    "case_id",
    "feature_id",
    "layer",
    "scenario_family",
    "business_rule_ids",
    "coverage_dimensions",
    "title",
    "objective",
    "sources",
    "confidence",
    "priority",
    "execution_type",
    "preconditions",
    "steps",
    "expected_result",
    "actual_result",
    "status",
    "data_contract",
    "evidence_required",
}
CONFIDENCE = {"confirmed", "inferred", "pending"}
PRIORITY = {"critical", "high", "medium", "low"}
EXECUTION_TYPES = {"manual", "automated", "both"}
CASE_STATUSES = {
    "NOT_EXECUTED",
    "PASSED",
    "FAILED",
    "BLOCKED",
    "SKIPPED",
}
LAYERS = {"frontend", "backend", "e2e", "data", "performance"}
SCENARIO_FAMILIES = {
    "happy-path",
    "alternate-path",
    "unhappy-path",
    "boundary",
    "state-transition",
    "authorization",
    "data-integrity",
    "contract",
    "integration",
    "resilience",
    "concurrency",
    "time",
    "calculation",
    "search-listing",
    "accessibility",
    "compatibility",
    "performance",
    "audit-observability",
}
SETUP_METHODS = {"api", "sql", "nosql", "ui", "fixture", "none"}
CLEANUP_METHODS = SETUP_METHODS
LAYER_PREFIXES = {
    "frontend": "FE-",
    "backend": "BE-",
    "e2e": "E2E-",
}


def load_document(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    coverage: dict[str, Any] = {}
    if isinstance(data, list):
        cases = data
    elif isinstance(data, dict) and isinstance(data.get("cases"), list):
        cases = data["cases"]
        raw_coverage = data.get("coverage", {})
        if not isinstance(raw_coverage, dict):
            raise ValueError("'coverage' must be an object")
        coverage = raw_coverage
    else:
        raise ValueError("Expected a JSON list or an object with a 'cases' list")
    if not all(isinstance(case, dict) for case in cases):
        raise ValueError("Every case must be a JSON object")
    return cases, coverage


def nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def nonempty_evidence(value: Any) -> bool:
    if nonempty_string(value):
        return True
    return isinstance(value, list) and bool(value)


def valid_blocker(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    status = value.get("status")
    reason = value.get("reason")
    evidence = value.get("evidence")
    valid_status = nonempty_string(status) and (
        status.startswith("BLOCKED_") or status == "NOT_APPLICABLE"
    )
    return bool(
        valid_status
        and nonempty_string(reason)
        and nonempty_evidence(evidence)
    )


def validate_case(case: dict[str, Any], index: int) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    label = case.get("case_id") or f"index:{index}"

    missing = sorted(REQUIRED_FIELDS - set(case))
    if missing:
        errors.append(f"{label}: missing fields: {', '.join(missing)}")

    for field in (
        "case_id",
        "feature_id",
        "title",
        "objective",
        "expected_result",
        "actual_result",
    ):
        if field in case and not nonempty_string(case[field]):
            errors.append(f"{label}: '{field}' must be a non-empty string")

    layer = case.get("layer")
    if layer not in LAYERS:
        errors.append(f"{label}: layer must be one of {sorted(LAYERS)}")
    elif layer in LAYER_PREFIXES and isinstance(case.get("case_id"), str):
        expected_prefix = LAYER_PREFIXES[layer]
        if not case["case_id"].startswith(expected_prefix):
            warnings.append(
                f"{label}: {layer} case_id should start with {expected_prefix}"
            )

    applicable_layers = case.get("applicable_layers")
    if applicable_layers is not None:
        if not isinstance(applicable_layers, list) or not applicable_layers:
            errors.append(f"{label}: applicable_layers must be a non-empty list")
        else:
            invalid_layers = sorted(set(applicable_layers) - LAYERS)
            if invalid_layers:
                errors.append(
                    f"{label}: invalid applicable_layers: {', '.join(invalid_layers)}"
                )
            if layer in LAYERS and layer not in applicable_layers:
                errors.append(
                    f"{label}: layer must be included in applicable_layers"
                )

    if case.get("confidence") not in CONFIDENCE:
        errors.append(
            f"{label}: confidence must be one of {sorted(CONFIDENCE)}"
        )
    if case.get("priority") not in PRIORITY:
        errors.append(f"{label}: priority must be one of {sorted(PRIORITY)}")
    if case.get("execution_type") not in EXECUTION_TYPES:
        errors.append(
            f"{label}: execution_type must be one of {sorted(EXECUTION_TYPES)}"
        )
    if case.get("status") not in CASE_STATUSES:
        errors.append(
            f"{label}: status must be one of {sorted(CASE_STATUSES)}"
        )

    scenario_family = case.get("scenario_family")
    if scenario_family not in SCENARIO_FAMILIES:
        errors.append(
            f"{label}: scenario_family must be one of "
            f"{sorted(SCENARIO_FAMILIES)}"
        )

    for field in ("business_rule_ids", "coverage_dimensions"):
        value = case.get(field)
        if not isinstance(value, list):
            errors.append(f"{label}: '{field}' must be a list")
            continue
        if not value:
            warnings.append(f"{label}: '{field}' is empty")
        invalid_values = [item for item in value if not nonempty_string(item)]
        if invalid_values:
            errors.append(f"{label}: '{field}' must contain non-empty strings")

    for field in ("sources", "preconditions", "evidence_required"):
        value = case.get(field)
        if not isinstance(value, list):
            errors.append(f"{label}: '{field}' must be a list")
        elif field == "sources" and not value:
            warnings.append(f"{label}: no source or evidence is linked")

    steps = case.get("steps")
    if not isinstance(steps, list) or not steps:
        errors.append(f"{label}: steps must be a non-empty list")
    else:
        orders: set[int] = set()
        for step_index, step in enumerate(steps, start=1):
            if not isinstance(step, dict):
                errors.append(f"{label}: step {step_index} must be an object")
                continue
            if not nonempty_string(step.get("action")):
                errors.append(f"{label}: step {step_index} needs an action")
            if not nonempty_string(step.get("expected")):
                errors.append(
                    f"{label}: step {step_index} needs an observable expected result"
                )
            order = step.get("order")
            if not isinstance(order, int) or order < 1:
                errors.append(f"{label}: step {step_index} has invalid order")
            elif order in orders:
                errors.append(f"{label}: duplicated step order {order}")
            else:
                orders.add(order)

    contract = case.get("data_contract")
    if not isinstance(contract, dict):
        errors.append(f"{label}: data_contract must be an object")
    else:
        if not nonempty_string(contract.get("dataset_id")):
            errors.append(f"{label}: data_contract.dataset_id is required")
        setup = contract.get("setup_method")
        cleanup = contract.get("cleanup_method")
        if setup not in SETUP_METHODS:
            errors.append(
                f"{label}: setup_method must be one of {sorted(SETUP_METHODS)}"
            )
        if cleanup not in CLEANUP_METHODS:
            errors.append(
                f"{label}: cleanup_method must be one of {sorted(CLEANUP_METHODS)}"
            )
        requirements = contract.get("requirements", [])
        if not isinstance(requirements, list):
            errors.append(f"{label}: data_contract.requirements must be a list")
        if setup != "none" and cleanup == "none":
            warnings.append(f"{label}: setup creates data but cleanup is none")

    automation = case.get("automation")
    if automation is not None:
        if not isinstance(automation, dict):
            errors.append(f"{label}: automation must be an object")
        elif automation.get("candidate") and not nonempty_string(
            automation.get("reason")
        ):
            warnings.append(f"{label}: automation candidate has no reason")

    derivation = case.get("derivation")
    if derivation is not None:
        if not isinstance(derivation, dict):
            errors.append(f"{label}: derivation must be an object")
        elif not nonempty_string(derivation.get("method")):
            warnings.append(f"{label}: derivation has no method")

    if case.get("confidence") == "pending":
        warnings.append(f"{label}: expected result still requires confirmation")

    return errors, warnings


def normalize_required_layers(
    cli_layers: Optional[list[str]],
    coverage: dict[str, Any],
) -> list[str]:
    raw_layers = cli_layers or coverage.get("required_layers") or [
        "frontend",
        "backend",
    ]
    if not isinstance(raw_layers, list) or not raw_layers:
        raise ValueError("required_layers must be a non-empty list")
    invalid = sorted(set(raw_layers) - LAYERS)
    if invalid:
        raise ValueError(f"Invalid required layers: {', '.join(invalid)}")
    return list(dict.fromkeys(raw_layers))


def normalize_required_scenarios(
    cli_scenarios: Optional[list[str]],
    coverage: dict[str, Any],
) -> list[str]:
    raw_scenarios = cli_scenarios
    if raw_scenarios is None:
        raw_scenarios = coverage.get("required_scenario_families", [])
    if not isinstance(raw_scenarios, list):
        raise ValueError("required_scenario_families must be a list")
    invalid = sorted(set(raw_scenarios) - SCENARIO_FAMILIES)
    if invalid:
        raise ValueError(
            f"Invalid required scenario families: {', '.join(invalid)}"
        )
    return list(dict.fromkeys(raw_scenarios))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument(
        "--require-layers",
        nargs="+",
        choices=sorted(LAYERS),
        help="Layers required for a complete delivery; defaults to coverage config or frontend backend.",
    )
    parser.add_argument(
        "--require-scenarios",
        nargs="+",
        choices=sorted(SCENARIO_FAMILIES),
        help="Scenario families required for every applicable feature and layer.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return failure when warnings are present.",
    )
    args = parser.parse_args()

    try:
        cases, coverage = load_document(args.input)
        required_layers = normalize_required_layers(args.require_layers, coverage)
        required_scenarios = normalize_required_scenarios(
            args.require_scenarios,
            coverage,
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"valid": False, "error": str(exc)}, indent=2))
        return 2

    errors: list[str] = []
    warnings: list[str] = []
    ids: set[str] = set()
    layer_counts: Counter[str] = Counter()
    scenario_counts: Counter[str] = Counter()
    business_rule_counts: Counter[str] = Counter()
    feature_layers: dict[str, set[str]] = defaultdict(set)
    feature_applicable_layers: dict[str, set[str]] = defaultdict(set)
    feature_layer_scenarios: dict[tuple[str, str], set[str]] = defaultdict(set)

    for index, case in enumerate(cases):
        case_errors, case_warnings = validate_case(case, index)
        errors.extend(case_errors)
        warnings.extend(case_warnings)
        case_id = case.get("case_id")
        if isinstance(case_id, str):
            if case_id in ids:
                errors.append(f"{case_id}: duplicate case_id")
            ids.add(case_id)

        layer = case.get("layer")
        feature_id = case.get("feature_id")
        if layer in LAYERS:
            layer_counts[layer] += 1
        if nonempty_string(feature_id) and layer in LAYERS:
            feature_layers[feature_id].add(layer)
            scenario_family = case.get("scenario_family")
            if scenario_family in SCENARIO_FAMILIES:
                feature_layer_scenarios[(feature_id, layer)].add(scenario_family)
                scenario_counts[scenario_family] += 1
            applicable = case.get("applicable_layers")
            if isinstance(applicable, list) and applicable:
                feature_applicable_layers[feature_id].update(applicable)
        rule_ids = case.get("business_rule_ids")
        if isinstance(rule_ids, list):
            for rule_id in rule_ids:
                if nonempty_string(rule_id):
                    business_rule_counts[rule_id] += 1

    blocked_layers = coverage.get("blocked_layers", {})
    if not isinstance(blocked_layers, dict):
        errors.append("coverage.blocked_layers must be an object")
        blocked_layers = {}
    blocked_features = coverage.get("blocked_features", {})
    if not isinstance(blocked_features, dict):
        errors.append("coverage.blocked_features must be an object")
        blocked_features = {}
    blocked_scenarios = coverage.get("blocked_scenarios", {})
    if not isinstance(blocked_scenarios, dict):
        errors.append("coverage.blocked_scenarios must be an object")
        blocked_scenarios = {}

    uncovered_layers: list[str] = []
    explicitly_blocked_layers: list[str] = []
    for layer in required_layers:
        if layer_counts[layer]:
            continue
        blocker = blocked_layers.get(layer)
        if valid_blocker(blocker):
            explicitly_blocked_layers.append(layer)
            warnings.append(
                f"coverage: {layer} is {blocker['status']}: {blocker['reason']}"
            )
        else:
            uncovered_layers.append(layer)
            errors.append(
                f"coverage: required layer '{layer}' has no cases and no valid blocker"
            )

    unpaired_features: dict[str, list[str]] = {}
    for feature_id, present_layers in sorted(feature_layers.items()):
        applicable_layers = (
            feature_applicable_layers.get(feature_id) or set(required_layers)
        )
        excluded = set(required_layers) - applicable_layers
        if excluded:
            cases_for_feature = [
                case for case in cases if case.get("feature_id") == feature_id
            ]
            if not any(
                nonempty_string(case.get("layer_scope_reason"))
                for case in cases_for_feature
            ):
                warnings.append(
                    f"{feature_id}: applicable_layers excludes "
                    f"{', '.join(sorted(excluded))} without layer_scope_reason"
                )

        missing_layers = sorted(
            (set(required_layers) & applicable_layers) - present_layers
        )
        if not missing_layers:
            continue

        unresolved: list[str] = []
        feature_blockers = blocked_features.get(feature_id, {})
        if not isinstance(feature_blockers, dict):
            feature_blockers = {}
        for layer in missing_layers:
            blocker = feature_blockers.get(layer)
            if valid_blocker(blocker):
                warnings.append(
                    f"{feature_id}: {layer} is {blocker['status']}: "
                    f"{blocker['reason']}"
                )
            else:
                unresolved.append(layer)
        if unresolved:
            unpaired_features[feature_id] = unresolved
            warnings.append(
                f"{feature_id}: missing related cases for "
                f"{', '.join(unresolved)}"
            )

    uncovered_scenarios: dict[str, dict[str, list[str]]] = {}
    explicitly_blocked_scenarios: list[str] = []
    for feature_id, present_layers in sorted(feature_layers.items()):
        applicable_layers = (
            feature_applicable_layers.get(feature_id) or set(required_layers)
        )
        for layer in sorted(set(required_layers) & applicable_layers & present_layers):
            missing_families = sorted(
                set(required_scenarios)
                - feature_layer_scenarios.get((feature_id, layer), set())
            )
            for family in missing_families:
                feature_blockers = blocked_scenarios.get(feature_id, {})
                if not isinstance(feature_blockers, dict):
                    feature_blockers = {}
                layer_blockers = feature_blockers.get(layer, {})
                if not isinstance(layer_blockers, dict):
                    layer_blockers = {}
                blocker = layer_blockers.get(family)
                if valid_blocker(blocker):
                    explicitly_blocked_scenarios.append(
                        f"{feature_id}:{layer}:{family}"
                    )
                    warnings.append(
                        f"{feature_id}: {layer}/{family} is "
                        f"{blocker['status']}: {blocker['reason']}"
                    )
                    continue
                uncovered_scenarios.setdefault(feature_id, {}).setdefault(
                    layer,
                    [],
                ).append(family)
                warnings.append(
                    f"{feature_id}: {layer} is missing required scenarios for "
                    f"{family}"
                )

    coverage_complete = not (
        uncovered_layers
        or explicitly_blocked_layers
        or unpaired_features
        or uncovered_scenarios
        or explicitly_blocked_scenarios
    )
    valid = not errors and not (args.strict and warnings)
    report = {
        "valid": valid,
        "delivery_status": (
            "INVALID"
            if errors
            else "COMPLETE"
            if coverage_complete
            else "PARTIAL"
        ),
        "coverage_complete": coverage_complete,
        "required_layers": required_layers,
        "required_scenario_families": required_scenarios,
        "layer_counts": {
            layer: layer_counts[layer]
            for layer in sorted(LAYERS)
        },
        "scenario_family_counts": {
            family: scenario_counts[family]
            for family in sorted(SCENARIO_FAMILIES)
        },
        "business_rule_count": len(business_rule_counts),
        "business_rule_case_counts": dict(sorted(business_rule_counts.items())),
        "uncovered_layers": uncovered_layers,
        "blocked_layers": explicitly_blocked_layers,
        "unpaired_features": unpaired_features,
        "uncovered_scenarios": uncovered_scenarios,
        "blocked_scenarios": explicitly_blocked_scenarios,
        "case_count": len(cases),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered + "\n", encoding="utf-8")

    if errors:
        return 1
    if args.strict and warnings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
