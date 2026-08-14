import json
import subprocess

import pytest
import yaml

from maestro_qa import repo_access
from maestro_qa.agents.bug_explorer import AGENT_REGISTRY, BugExplorerAgent
from maestro_qa.orchestrator import Intake

VALID_PAYLOAD_WITH_CAUSE = {
    "likely_causes": [
        {
            "file": "pages/login_page.py",
            "line": 27,
            "confidence": "alta",
            "reasoning": "El handler de submit no espera la respuesta del OAuth antes de redirigir",
            "suggested_direction": "Revisar el await del callback de Google antes del router.push",
        }
    ],
    "pending_items": [],
}

VALID_PAYLOAD_EMPTY = {"likely_causes": [], "pending_items": []}


class FakeProvider:
    def __init__(self, response: str):
        self._response = response

    def complete(self, system, messages, **kwargs):
        return self._response


def test_registers_itself():
    assert isinstance(AGENT_REGISTRY["bug_explorer"], BugExplorerAgent)


def test_likely_cause_renders_as_markdown_with_file_line_and_direction():
    provider = FakeProvider(json.dumps(VALID_PAYLOAD_WITH_CAUSE))
    intake = Intake(source="jira_ticket", text="el login con Google no redirige al dashboard")

    result = BugExplorerAgent().run(intake, provider)

    assert result.agent == "bug_explorer"
    assert "[alta] pages/login_page.py:27" in result.content
    assert "no espera la respuesta del OAuth" in result.content
    assert "Revisar: Revisar el await" in result.content


def test_conceptual_cause_without_file_renders_without_fabricating_a_path():
    payload = {
        "likely_causes": [
            {
                "file": None,
                "line": None,
                "confidence": "media",
                "reasoning": "Probablemente el handler de submit no espera el callback de OAuth",
                "suggested_direction": None,
            }
        ],
        "pending_items": [],
    }
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="spec", text="el login con Google no redirige")

    result = BugExplorerAgent().run(intake, provider)

    assert "(hipótesis conceptual, sin repo real)" in result.content
    assert "Probablemente el handler" in result.content


def test_empty_causes_is_a_valid_result_not_an_error():
    provider = FakeProvider(json.dumps(VALID_PAYLOAD_EMPTY))
    intake = Intake(source="spec", text="algo falla pero no hay detalle")

    result = BugExplorerAgent().run(intake, provider)

    assert "Sin causas identificadas" in result.content


def test_pending_items_are_surfaced_when_description_is_insufficient():
    payload = {"likely_causes": [], "pending_items": ["Falta el mensaje de error real y los pasos para reproducir"]}
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="spec", text="algo anda mal")

    result = BugExplorerAgent().run(intake, provider)

    assert "Falta el mensaje de error real" in result.content


@pytest.mark.parametrize("missing_field", ["confidence", "reasoning"])
def test_cause_missing_required_field_raises_clear_error_not_keyerror(missing_field):
    cause = dict(VALID_PAYLOAD_WITH_CAUSE["likely_causes"][0])
    del cause[missing_field]
    payload = {"likely_causes": [cause], "pending_items": []}
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="jira_ticket", text="el login con Google no redirige")

    with pytest.raises(ValueError, match=missing_field):
        BugExplorerAgent().run(intake, provider)


def test_invalid_confidence_raises():
    cause = {**VALID_PAYLOAD_WITH_CAUSE["likely_causes"][0], "confidence": "segurísima"}
    payload = {"likely_causes": [cause], "pending_items": []}
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="jira_ticket", text="el login con Google no redirige")

    with pytest.raises(ValueError, match="confidence inválida"):
        BugExplorerAgent().run(intake, provider)


def test_likely_causes_not_a_list_raises_clear_error():
    payload = {"likely_causes": "una sola causa", "pending_items": []}
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="jira_ticket", text="el login con Google no redirige")

    with pytest.raises(ValueError, match="likely_causes debe ser una lista"):
        BugExplorerAgent().run(intake, provider)


def test_response_wrapped_in_markdown_fence_is_still_parsed():
    provider = FakeProvider(f"```json\n{json.dumps(VALID_PAYLOAD_EMPTY)}\n```")
    intake = Intake(source="spec", text="algo falla")

    result = BugExplorerAgent().run(intake, provider)
    assert "Sin causas identificadas" in result.content


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def frontend_project(tmp_path, monkeypatch):
    remote = tmp_path / "remote"
    remote.mkdir()
    _git(["init", "-q", "--initial-branch=main"], remote)
    _git(["config", "user.email", "test@example.com"], remote)
    _git(["config", "user.name", "Test"], remote)
    (remote / "src").mkdir()
    (remote / "src" / "login.jsx").write_text("export const Login = () => <button>Login</button>\n")
    _git(["add", "-A"], remote)
    _git(["commit", "-q", "-m", "init"], remote)

    qa_project = tmp_path / "qa-project.yaml"
    qa_project.write_text(
        yaml.safe_dump({"repositories": {"frontend": {"url": str(remote), "branch": "main"}}}), encoding="utf-8"
    )
    monkeypatch.setattr(repo_access, "_CACHE_ROOT", tmp_path / "cache")
    monkeypatch.chdir(tmp_path)
    return remote


class ReadOnlyToolProvider:
    def __init__(self, response: str):
        self._response = response
        self.received_tools = None

    def complete(self, system, messages, tools=None, tool_executor=None, **kwargs):
        assert tool_executor is not None
        self.received_tools = tools
        tool_executor("list_files", {"path": "."})
        self.write_result = tool_executor("write_file", {"path": "src/login.jsx", "content": "hackeado"})
        return self._response


def test_only_read_only_tools_are_offered_and_write_file_is_rejected(frontend_project):
    provider = ReadOnlyToolProvider(json.dumps(VALID_PAYLOAD_EMPTY))
    intake = Intake(source="jira_ticket", text="el login con Google no redirige")

    BugExplorerAgent().run(intake, provider)

    tool_names = {tool["name"] for tool in provider.received_tools}
    assert tool_names == {"list_files", "read_file"}
    assert provider.write_result.startswith("error:")
    assert (frontend_project / "src" / "login.jsx").exists()


def test_falls_back_to_reasoning_from_description_without_frontend_repo_configured(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    provider = FakeProvider(json.dumps(VALID_PAYLOAD_EMPTY))
    intake = Intake(source="jira_ticket", text="el login con Google no redirige")

    result = BugExplorerAgent().run(intake, provider)

    assert "Sin causas identificadas" in result.content


def test_repo_access_failure_is_surfaced_as_pending_item_not_a_crash(tmp_path, monkeypatch):
    qa_project = tmp_path / "qa-project.yaml"
    qa_project.write_text(
        yaml.safe_dump({"repositories": {"frontend": {"url": str(tmp_path / "no-existe"), "branch": "main"}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(repo_access, "_CACHE_ROOT", tmp_path / "cache")
    monkeypatch.chdir(tmp_path)

    provider = FakeProvider(json.dumps(VALID_PAYLOAD_EMPTY))
    intake = Intake(source="jira_ticket", text="el login con Google no redirige")

    result = BugExplorerAgent().run(intake, provider)

    assert "No se pudo usar el repo de frontend" in result.content


def test_tool_calling_failure_falls_back_to_reasoning_without_repo_access(frontend_project):
    intake = Intake(source="jira_ticket", text="el login con Google no redirige")

    class SequencedProvider:
        def complete(self, system, messages, tools=None, tool_executor=None, **kwargs):
            if tools is not None:
                raise RuntimeError("el provider explotó a mitad del tool-calling")
            return json.dumps(VALID_PAYLOAD_EMPTY)

    result = BugExplorerAgent().run(intake, SequencedProvider())

    assert "Sin causas identificadas" in result.content
    assert "tool-calling falló" in result.content
