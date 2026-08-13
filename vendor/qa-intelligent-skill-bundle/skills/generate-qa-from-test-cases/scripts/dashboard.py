#!/usr/bin/env python3
"""Read-only Streamlit dashboard for qa_history.py data."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def metadata_value(raw: object, key: str) -> object:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(value, dict):
        return None
    return value.get(key)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--history-dir", type=Path, default=Path("qa-history"))
    args, _ = parser.parse_known_args()
    return args


def main() -> None:
    try:
        import pandas as pd  # type: ignore
        import streamlit as st  # type: ignore
    except ImportError as exc:
        raise SystemExit(
            "This dashboard requires streamlit and pandas in an isolated environment."
        ) from exc

    args = parse_args()
    db_path = args.history_dir / "qa-history.db"

    st.set_page_config(page_title="QA History", layout="wide")
    st.title("QA History")
    st.caption(f"Read-only history: {db_path}")

    if not db_path.exists():
        st.error("History database not found. Run qa_history.py init first.")
        return

    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        runs = pd.read_sql_query(
            "SELECT * FROM runs ORDER BY started_utc DESC",
            connection,
        )
        events = pd.read_sql_query(
            "SELECT * FROM events ORDER BY timestamp_utc DESC",
            connection,
        )
    finally:
        connection.close()

    if not events.empty and "metadata_json" in events.columns:
        events["data_status"] = events["metadata_json"].apply(
            lambda raw: metadata_value(raw, "data_status")
        )
        events["data_count"] = events["metadata_json"].apply(
            lambda raw: metadata_value(raw, "row_count")
            or metadata_value(raw, "document_count")
        )
        events["cleanup_status"] = events["metadata_json"].apply(
            lambda raw: metadata_value(raw, "cleanup_status")
        )
        events["external_service"] = events["metadata_json"].apply(
            lambda raw: metadata_value(raw, "external_service")
            or metadata_value(raw, "service")
        )
        events["dependency_mode"] = events["metadata_json"].apply(
            lambda raw: metadata_value(raw, "external_dependency_mode")
            or metadata_value(raw, "mode")
        )
        events["mock_scenario"] = events["metadata_json"].apply(
            lambda raw: metadata_value(raw, "mock_scenario")
            or metadata_value(raw, "scenario")
        )
        events["contract_version"] = events["metadata_json"].apply(
            lambda raw: metadata_value(raw, "contract_version")
        )

    projects = sorted(runs["project"].dropna().unique().tolist()) if not runs.empty else []
    statuses = (
        sorted(events["status"].dropna().unique().tolist()) if not events.empty else []
    )
    modules = (
        sorted(events["module"].dropna().unique().tolist()) if not events.empty else []
    )

    selected_projects = st.sidebar.multiselect("Projects", projects, projects)
    selected_statuses = st.sidebar.multiselect("Event status", statuses, statuses)
    selected_modules = st.sidebar.multiselect("Modules", modules, modules)
    case_filter = st.sidebar.text_input("Case ID contains")
    run_filter = st.sidebar.text_input("Run ID contains")

    filtered_runs = runs.copy()
    filtered_events = events.copy()
    if selected_projects:
        filtered_runs = filtered_runs[filtered_runs["project"].isin(selected_projects)]
        filtered_events = filtered_events[
            filtered_events["project"].isin(selected_projects)
        ]
    if selected_statuses:
        filtered_events = filtered_events[
            filtered_events["status"].isin(selected_statuses)
        ]
    if selected_modules:
        filtered_events = filtered_events[
            filtered_events["module"].isin(selected_modules)
        ]
    if case_filter:
        filtered_events = filtered_events[
            filtered_events["case_id"]
            .fillna("")
            .str.contains(case_filter, case=False, regex=False)
        ]
    if run_filter:
        filtered_runs = filtered_runs[
            filtered_runs["run_id"].str.contains(run_filter, case=False, regex=False)
        ]
        filtered_events = filtered_events[
            filtered_events["run_id"].str.contains(
                run_filter, case=False, regex=False
            )
        ]

    metric_columns = st.columns(5)
    metric_columns[0].metric("Runs", len(filtered_runs))
    metric_columns[1].metric("Events", len(filtered_events))
    metric_columns[2].metric(
        "Passed", int((filtered_events["status"] == "PASSED").sum())
    )
    metric_columns[3].metric(
        "Failed", int((filtered_events["status"] == "FAILED").sum())
    )
    metric_columns[4].metric(
        "Blocked", int((filtered_events["status"] == "BLOCKED").sum())
    )

    left, right = st.columns(2)
    with left:
        st.subheader("Runs by status")
        if filtered_runs.empty:
            st.info("No runs for the selected filters.")
        else:
            run_status = filtered_runs["status"].value_counts().rename("count")
            st.bar_chart(run_status)
    with right:
        st.subheader("Events by status")
        if filtered_events.empty:
            st.info("No events for the selected filters.")
        else:
            event_status = filtered_events["status"].value_counts().rename("count")
            st.bar_chart(event_status)

    st.subheader("Runs")
    st.dataframe(
        filtered_runs,
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("Timeline")
    visible_columns = [
        "timestamp_utc",
        "run_id",
        "project",
        "module",
        "action",
        "target",
        "status",
        "case_id",
        "dataset_id",
        "summary",
        "artifact_path",
        "error_code",
    ]
    st.dataframe(
        filtered_events[visible_columns] if not filtered_events.empty else filtered_events,
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("Datos por tabla o colección")
    if filtered_events.empty:
        st.info("No data events for the selected filters.")
    else:
        data_events = filtered_events[
            (filtered_events["module"] == "data")
            & filtered_events["action"].isin(
                [
                    "dataset-generated",
                    "seed-planned",
                    "seed-inserted",
                    "verification-queries-generated",
                    "cleanup-completed",
                ]
            )
        ]
        data_columns = [
            "timestamp_utc",
            "run_id",
            "project",
            "action",
            "target",
            "status",
            "data_status",
            "data_count",
            "cleanup_status",
            "dataset_id",
            "summary",
            "artifact_path",
        ]
        if data_events.empty:
            st.info("No generated, seeded, or cleaned data for the selected filters.")
        else:
            st.dataframe(
                data_events[data_columns],
                use_container_width=True,
                hide_index=True,
            )

    st.subheader("Dependencias externas")
    if filtered_events.empty:
        st.info("No external dependency events for the selected filters.")
    else:
        external_events = filtered_events[
            filtered_events["action"].isin(
                [
                    "mock-catalog-validated",
                    "mock-started",
                    "mock-scenario-used",
                    "mock-stopped",
                    "real-sandbox-used",
                ]
            )
        ]
        external_columns = [
            "timestamp_utc",
            "run_id",
            "project",
            "action",
            "status",
            "external_service",
            "dependency_mode",
            "mock_scenario",
            "contract_version",
            "case_id",
            "summary",
            "artifact_path",
        ]
        if external_events.empty:
            st.info("No mock or sandbox events for the selected filters.")
        else:
            st.dataframe(
                external_events[external_columns],
                use_container_width=True,
                hide_index=True,
            )

    st.download_button(
        "Download filtered events CSV",
        filtered_events.to_csv(index=False).encode("utf-8"),
        file_name="qa-events-filtered.csv",
        mime="text/csv",
    )


if __name__ == "__main__":
    main()
