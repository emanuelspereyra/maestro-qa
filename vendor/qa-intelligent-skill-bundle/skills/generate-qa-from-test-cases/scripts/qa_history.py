#!/usr/bin/env python3
"""Maintain an append-only QA event log and a queryable SQLite history."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sqlite3
import uuid
from pathlib import Path
from typing import Any


SENSITIVE_KEY = re.compile(
    r"(password|passwd|secret|token|cookie|authorization|credential|connection.?string)",
    re.IGNORECASE,
)
VALID_STATUSES = {
    "PLANNED",
    "GENERATED",
    "STARTED",
    "EXECUTED",
    "VERIFIED",
    "PASSED",
    "FAILED",
    "BLOCKED",
    "SKIPPED",
    "COMPLETED",
    "CANCELLED",
}


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sanitize(value: Any, key: str = "") -> Any:
    if SENSITIVE_KEY.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): sanitize(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize(item) for item in value]
    return value


def history_paths(history_dir: Path) -> tuple[Path, Path, Path]:
    return (
        history_dir / "qa-history.db",
        history_dir / "events.jsonl",
        history_dir / "runs",
    )


def connect(history_dir: Path) -> sqlite3.Connection:
    history_dir.mkdir(parents=True, exist_ok=True)
    db_path, _, runs_dir = history_paths(history_dir)
    runs_dir.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS runs (
          run_id TEXT PRIMARY KEY,
          project TEXT NOT NULL,
          started_utc TEXT NOT NULL,
          ended_utc TEXT,
          status TEXT NOT NULL,
          metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS events (
          event_id TEXT PRIMARY KEY,
          timestamp_utc TEXT NOT NULL,
          run_id TEXT NOT NULL,
          project TEXT NOT NULL,
          module TEXT NOT NULL,
          action TEXT NOT NULL,
          target TEXT,
          status TEXT NOT NULL,
          duration_ms INTEGER,
          case_id TEXT,
          dataset_id TEXT,
          summary TEXT,
          artifact_path TEXT,
          error_code TEXT,
          metadata_json TEXT NOT NULL DEFAULT '{}',
          FOREIGN KEY (run_id) REFERENCES runs(run_id)
        );

        CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id);
        CREATE INDEX IF NOT EXISTS idx_events_status ON events(status);
        CREATE INDEX IF NOT EXISTS idx_events_case ON events(case_id);
        CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp_utc);
        """
    )
    connection.commit()
    return connection


def append_jsonl(history_dir: Path, event: dict[str, Any]) -> None:
    _, events_path, _ = history_paths(history_dir)
    with events_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")


def parse_metadata(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("metadata must be a JSON object")
    return sanitize(value)


def insert_event(connection: sqlite3.Connection, event: dict[str, Any]) -> None:
    connection.execute(
        """
        INSERT INTO events (
          event_id, timestamp_utc, run_id, project, module, action, target,
          status, duration_ms, case_id, dataset_id, summary, artifact_path,
          error_code, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event["event_id"],
            event["timestamp_utc"],
            event["run_id"],
            event["project"],
            event["module"],
            event["action"],
            event.get("target"),
            event["status"],
            event.get("duration_ms"),
            event.get("case_id"),
            event.get("dataset_id"),
            event.get("summary"),
            event.get("artifact_path"),
            event.get("error_code"),
            json.dumps(event.get("metadata", {}), ensure_ascii=False, default=str),
        ),
    )
    connection.commit()


def get_run(connection: sqlite3.Connection, run_id: str) -> sqlite3.Row:
    row = connection.execute(
        "SELECT * FROM runs WHERE run_id = ?", (run_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"Unknown run_id: {run_id}")
    return row


def write_run_summary(history_dir: Path, run_id: str) -> None:
    connection = connect(history_dir)
    try:
        run = get_run(connection, run_id)
        events = connection.execute(
            """
            SELECT event_id, timestamp_utc, module, action, target, status,
                   duration_ms, case_id, dataset_id, summary, artifact_path,
                   error_code, metadata_json
            FROM events
            WHERE run_id = ?
            ORDER BY timestamp_utc, event_id
            """,
            (run_id,),
        ).fetchall()
        summary = {
            "run": dict(run),
            "events": [
                {
                    **{
                        key: event[key]
                        for key in event.keys()
                        if key != "metadata_json"
                    },
                    "metadata": json.loads(event["metadata_json"]),
                }
                for event in events
            ],
        }
        _, _, runs_dir = history_paths(history_dir)
        (runs_dir / f"{run_id}.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    finally:
        connection.close()


def start_run(args: argparse.Namespace) -> str:
    connection = connect(args.history_dir)
    try:
        run_id = args.run_id or str(uuid.uuid4())
        timestamp = now_utc()
        metadata = parse_metadata(args.metadata_json)
        connection.execute(
            """
            INSERT INTO runs (
              run_id, project, started_utc, status, metadata_json
            ) VALUES (?, ?, ?, 'STARTED', ?)
            """,
            (
                run_id,
                args.project,
                timestamp,
                json.dumps(metadata, ensure_ascii=False),
            ),
        )
        event = {
            "event_id": str(uuid.uuid4()),
            "timestamp_utc": timestamp,
            "run_id": run_id,
            "project": args.project,
            "module": "run",
            "action": "start-run",
            "target": None,
            "status": "STARTED",
            "duration_ms": None,
            "case_id": None,
            "dataset_id": None,
            "summary": args.summary,
            "artifact_path": None,
            "error_code": None,
            "metadata": metadata,
        }
        insert_event(connection, event)
        append_jsonl(args.history_dir, event)
        return run_id
    finally:
        connection.close()


def log_event(args: argparse.Namespace) -> str:
    status = args.status.upper()
    if status not in VALID_STATUSES:
        raise ValueError(
            f"Invalid status '{args.status}'; choose one of {sorted(VALID_STATUSES)}"
        )
    connection = connect(args.history_dir)
    try:
        run = get_run(connection, args.run_id)
        event = {
            "event_id": args.event_id or str(uuid.uuid4()),
            "timestamp_utc": now_utc(),
            "run_id": args.run_id,
            "project": run["project"],
            "module": args.module,
            "action": args.action,
            "target": args.target,
            "status": status,
            "duration_ms": args.duration_ms,
            "case_id": args.case_id,
            "dataset_id": args.dataset_id,
            "summary": args.summary,
            "artifact_path": args.artifact_path,
            "error_code": args.error_code,
            "metadata": parse_metadata(args.metadata_json),
        }
        insert_event(connection, event)
        append_jsonl(args.history_dir, event)
        return event["event_id"]
    finally:
        connection.close()


def end_run(args: argparse.Namespace) -> None:
    status = args.status.upper()
    if status not in {"COMPLETED", "FAILED", "BLOCKED", "CANCELLED"}:
        raise ValueError("Run status must be COMPLETED, FAILED, BLOCKED or CANCELLED")
    connection = connect(args.history_dir)
    try:
        run = get_run(connection, args.run_id)
        timestamp = now_utc()
        connection.execute(
            "UPDATE runs SET ended_utc = ?, status = ? WHERE run_id = ?",
            (timestamp, status, args.run_id),
        )
        event = {
            "event_id": str(uuid.uuid4()),
            "timestamp_utc": timestamp,
            "run_id": args.run_id,
            "project": run["project"],
            "module": "run",
            "action": "end-run",
            "target": None,
            "status": status,
            "duration_ms": None,
            "case_id": None,
            "dataset_id": None,
            "summary": args.summary,
            "artifact_path": None,
            "error_code": args.error_code,
            "metadata": parse_metadata(args.metadata_json),
        }
        insert_event(connection, event)
        append_jsonl(args.history_dir, event)
    finally:
        connection.close()
    write_run_summary(args.history_dir, args.run_id)


def summary(args: argparse.Namespace) -> dict[str, Any]:
    connection = connect(args.history_dir)
    try:
        run_counts = {
            row["status"]: row["count"]
            for row in connection.execute(
                "SELECT status, COUNT(*) AS count FROM runs GROUP BY status"
            ).fetchall()
        }
        event_counts = {
            row["status"]: row["count"]
            for row in connection.execute(
                "SELECT status, COUNT(*) AS count FROM events GROUP BY status"
            ).fetchall()
        }
        projects = [
            dict(row)
            for row in connection.execute(
                """
                SELECT project, COUNT(*) AS runs, MAX(started_utc) AS last_started_utc
                FROM runs GROUP BY project ORDER BY project
                """
            ).fetchall()
        ]
        return {
            "runs_by_status": run_counts,
            "events_by_status": event_counts,
            "projects": projects,
        }
    finally:
        connection.close()


def export_csv(args: argparse.Namespace) -> int:
    connection = connect(args.history_dir)
    try:
        rows = connection.execute(
            "SELECT * FROM events ORDER BY timestamp_utc, event_id"
        ).fetchall()
        columns = [description[0] for description in connection.execute(
            "SELECT * FROM events LIMIT 0"
        ).description]
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(columns)
            writer.writerows([row[column] for column in columns] for row in rows)
        return len(rows)
    finally:
        connection.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("--history-dir", type=Path, default=Path("qa-history"))

    start = subparsers.add_parser("start-run")
    start.add_argument("--history-dir", type=Path, default=Path("qa-history"))
    start.add_argument("--project", required=True)
    start.add_argument("--run-id")
    start.add_argument("--summary")
    start.add_argument("--metadata-json")

    log = subparsers.add_parser("log")
    log.add_argument("--history-dir", type=Path, default=Path("qa-history"))
    log.add_argument("--run-id", required=True)
    log.add_argument("--event-id")
    log.add_argument("--module", required=True)
    log.add_argument("--action", required=True)
    log.add_argument("--target")
    log.add_argument("--status", required=True)
    log.add_argument("--duration-ms", type=int)
    log.add_argument("--case-id")
    log.add_argument("--dataset-id")
    log.add_argument("--summary")
    log.add_argument("--artifact-path")
    log.add_argument("--error-code")
    log.add_argument("--metadata-json")

    end = subparsers.add_parser("end-run")
    end.add_argument("--history-dir", type=Path, default=Path("qa-history"))
    end.add_argument("--run-id", required=True)
    end.add_argument("--status", default="COMPLETED")
    end.add_argument("--summary")
    end.add_argument("--error-code")
    end.add_argument("--metadata-json")

    summary_parser = subparsers.add_parser("summary")
    summary_parser.add_argument(
        "--history-dir", type=Path, default=Path("qa-history")
    )

    export = subparsers.add_parser("export")
    export.add_argument("--history-dir", type=Path, default=Path("qa-history"))
    export.add_argument("--output", type=Path, required=True)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.command == "init":
            connection = connect(args.history_dir)
            connection.close()
            print(json.dumps({"initialized": str(args.history_dir)}, indent=2))
        elif args.command == "start-run":
            run_id = start_run(args)
            print(json.dumps({"run_id": run_id}, indent=2))
        elif args.command == "log":
            event_id = log_event(args)
            print(json.dumps({"event_id": event_id}, indent=2))
        elif args.command == "end-run":
            end_run(args)
            print(json.dumps({"run_id": args.run_id, "status": args.status}, indent=2))
        elif args.command == "summary":
            print(json.dumps(summary(args), ensure_ascii=False, indent=2))
        elif args.command == "export":
            count = export_csv(args)
            print(json.dumps({"output": str(args.output), "rows": count}, indent=2))
        return 0
    except (OSError, ValueError, json.JSONDecodeError, sqlite3.Error) as exc:
        print(
            json.dumps(
                {"ok": False, "error": type(exc).__name__, "message": str(exc)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
