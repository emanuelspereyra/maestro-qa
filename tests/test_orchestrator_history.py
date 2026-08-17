import sqlite3

from maestro_qa.agents.registry import AGENT_REGISTRY
from maestro_qa.orchestrator import AgentResult, Intake, run


class FakeAgent:
    def __init__(self, name, content="ok", raises=False):
        self.name = name
        self.content = content
        self.raises = raises

    def run(self, intake, provider):
        if self.raises:
            raise RuntimeError(f"{self.name} broke")
        return AgentResult(agent=self.name, content=self.content)


def _events(history_dir):
    connection = sqlite3.connect(history_dir / "qa-history.db")
    try:
        return connection.execute("SELECT module, status FROM events").fetchall()
    finally:
        connection.close()


def _events_with_error_code(history_dir):
    connection = sqlite3.connect(history_dir / "qa-history.db")
    try:
        return connection.execute("SELECT module, error_code FROM events").fetchall()
    finally:
        connection.close()


def test_no_history_dir_means_no_side_effects(tmp_path, monkeypatch):
    original = dict(AGENT_REGISTRY)
    AGENT_REGISTRY.clear()
    AGENT_REGISTRY["casos_manuales"] = FakeAgent("casos_manuales")
    monkeypatch.chdir(tmp_path)

    run(Intake(source="spec", text="feature sin keywords"), provider=None)

    assert not (tmp_path / "qa-history").exists()
    AGENT_REGISTRY.clear()
    AGENT_REGISTRY.update(original)


def test_history_dir_records_one_event_per_agent(tmp_path):
    original = dict(AGENT_REGISTRY)
    AGENT_REGISTRY.clear()
    AGENT_REGISTRY["casos_manuales"] = FakeAgent("casos_manuales", content="3 casos")
    AGENT_REGISTRY["trazabilidad"] = FakeAgent("trazabilidad", content="100% cubierto")

    history_dir = tmp_path / "qa-history"
    run(Intake(source="jira_ticket", text="feature sin keywords"), provider=None, history_dir=history_dir)

    assert (history_dir / "qa-history.db").exists()
    assert (history_dir / "events.jsonl").exists()
    events = _events(history_dir)
    assert ("casos_manuales", "EXECUTED") in events
    assert ("trazabilidad", "EXECUTED") in events

    AGENT_REGISTRY.clear()
    AGENT_REGISTRY.update(original)


def test_failed_agent_is_logged_as_failed_not_hidden(tmp_path):
    original = dict(AGENT_REGISTRY)
    AGENT_REGISTRY.clear()
    AGENT_REGISTRY["casos_manuales"] = FakeAgent("casos_manuales", raises=True)
    AGENT_REGISTRY["trazabilidad"] = FakeAgent("trazabilidad")

    history_dir = tmp_path / "qa-history"
    run(Intake(source="spec", text="feature sin keywords"), provider=None, history_dir=history_dir)

    events = dict(_events(history_dir))
    assert events["casos_manuales"] == "FAILED"
    assert events["trazabilidad"] == "EXECUTED"

    AGENT_REGISTRY.clear()
    AGENT_REGISTRY.update(original)


def test_failed_agent_records_exception_type_as_error_code(tmp_path):
    original = dict(AGENT_REGISTRY)
    AGENT_REGISTRY.clear()
    AGENT_REGISTRY["casos_manuales"] = FakeAgent("casos_manuales", raises=True)
    AGENT_REGISTRY["trazabilidad"] = FakeAgent("trazabilidad")

    history_dir = tmp_path / "qa-history"
    run(Intake(source="spec", text="feature sin keywords"), provider=None, history_dir=history_dir)

    error_codes = dict(_events_with_error_code(history_dir))
    assert error_codes["casos_manuales"] == "RuntimeError"
    assert error_codes["trazabilidad"] is None

    AGENT_REGISTRY.clear()
    AGENT_REGISTRY.update(original)


def test_agent_result_without_error_code_keeps_working(tmp_path):
    result = AgentResult(agent="trazabilidad", content="100% cubierto")

    assert result.error_code is None
    assert result.error is False
