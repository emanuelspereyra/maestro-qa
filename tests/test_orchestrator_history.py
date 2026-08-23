import sqlite3

from maestro_qa import orchestrator
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


class FakeClock:
    def __init__(self, ticks):
        self.ticks = iter(ticks)

    def __call__(self):
        return next(self.ticks)


def _events(history_dir):
    connection = sqlite3.connect(history_dir / "qa-history.db")
    try:
        return connection.execute("SELECT module, status FROM events").fetchall()
    finally:
        connection.close()


def _durations(history_dir):
    connection = sqlite3.connect(history_dir / "qa-history.db")
    try:
        return connection.execute("SELECT module, status, duration_ms FROM events").fetchall()
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


def test_successful_agent_persists_expected_duration_ms(tmp_path, monkeypatch):
    original = dict(AGENT_REGISTRY)
    AGENT_REGISTRY.clear()
    AGENT_REGISTRY["casos_manuales"] = FakeAgent("casos_manuales", content="3 casos")
    monkeypatch.setattr(orchestrator, "perf_counter", FakeClock([0.0, 1.5]))

    history_dir = tmp_path / "qa-history"
    result = run(Intake(source="spec", text="feature sin keywords"), provider=None, history_dir=history_dir)

    assert ("casos_manuales", "EXECUTED", 1500) in _durations(history_dir)
    assert result.results[0].duration_ms == 1500

    AGENT_REGISTRY.clear()
    AGENT_REGISTRY.update(original)


def test_failed_agent_also_persists_duration_ms(tmp_path, monkeypatch):
    original = dict(AGENT_REGISTRY)
    AGENT_REGISTRY.clear()
    AGENT_REGISTRY["casos_manuales"] = FakeAgent("casos_manuales", raises=True)
    monkeypatch.setattr(orchestrator, "perf_counter", FakeClock([0.0, 0.25]))

    history_dir = tmp_path / "qa-history"
    result = run(Intake(source="spec", text="feature sin keywords"), provider=None, history_dir=history_dir)

    assert ("casos_manuales", "FAILED", 250) in _durations(history_dir)
    assert result.results[0].error is True
    assert result.results[0].duration_ms == 250

    AGENT_REGISTRY.clear()
    AGENT_REGISTRY.update(original)


def test_log_history_without_duration_omits_flag(tmp_path, monkeypatch):
    captured = {}

    def fake_call(history_dir, *args):
        captured["args"] = args
        return {"run_id": "run-1"}

    monkeypatch.setattr(orchestrator, "_history_call", fake_call)

    orchestrator._log_history(
        tmp_path, "run-1", AgentResult(agent="casos_manuales", content="ok")
    )

    assert "--duration-ms" not in captured["args"]


def test_log_history_with_duration_passes_flag_in_ms(tmp_path, monkeypatch):
    captured = {}

    def fake_call(history_dir, *args):
        captured["args"] = args
        return {"run_id": "run-1"}

    monkeypatch.setattr(orchestrator, "_history_call", fake_call)

    orchestrator._log_history(
        tmp_path,
        "run-1",
        AgentResult(agent="casos_manuales", content="ok", duration_ms=1500),
    )

    args = captured["args"]
    assert "--duration-ms" in args
    assert args[args.index("--duration-ms") + 1] == "1500"
