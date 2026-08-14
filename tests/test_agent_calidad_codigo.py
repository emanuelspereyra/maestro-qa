import json
import subprocess

import pytest
import yaml

from maestro_qa import repo_access
from maestro_qa.agents.calidad_codigo import AGENT_REGISTRY, CalidadCodigoAgent
from maestro_qa.orchestrator import Intake

VALID_PAYLOAD_WITH_FINDINGS = {
    "findings": [
        {
            "location": "pages/login_page.py:12",
            "severity": "media",
            "problem": "Wrapper de una sola línea sobre self.page.click() sin agregar nada",
            "suggestion": "Eliminar el wrapper y llamar self.page.click() directo",
        }
    ],
    "pending_items": [],
}

VALID_PAYLOAD_CLEAN = {"findings": [], "pending_items": []}


class FakeProvider:
    def __init__(self, response: str):
        self._response = response

    def complete(self, system, messages, **kwargs):
        return self._response


def test_registers_itself():
    assert isinstance(AGENT_REGISTRY["calidad_codigo"], CalidadCodigoAgent)


def test_findings_render_as_markdown_with_severity_and_suggestion():
    provider = FakeProvider(json.dumps(VALID_PAYLOAD_WITH_FINDINGS))
    intake = Intake(source="spec", text="revisar código del login")

    result = CalidadCodigoAgent().run(intake, provider)

    assert result.agent == "calidad_codigo"
    assert "[media] pages/login_page.py:12" in result.content
    assert "Wrapper de una sola línea" in result.content
    assert "Eliminar el wrapper" in result.content


def test_empty_findings_is_a_valid_clean_result_not_an_error():
    provider = FakeProvider(json.dumps(VALID_PAYLOAD_CLEAN))
    intake = Intake(source="spec", text="revisar código del login")

    result = CalidadCodigoAgent().run(intake, provider)

    assert "Sin hallazgos" in result.content


def test_pending_items_are_surfaced_when_nothing_to_review():
    payload = {"findings": [], "pending_items": ["No había código real en el mensaje ni repo configurado"]}
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="spec", text="revisar código, pero sin pegar nada")

    result = CalidadCodigoAgent().run(intake, provider)

    assert "No había código real" in result.content


@pytest.mark.parametrize("missing_field", ["location", "severity", "problem", "suggestion"])
def test_finding_missing_required_field_raises_clear_error_not_keyerror(missing_field):
    finding = dict(VALID_PAYLOAD_WITH_FINDINGS["findings"][0])
    del finding[missing_field]
    payload = {"findings": [finding], "pending_items": []}
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="spec", text="revisar código del login")

    with pytest.raises(ValueError, match=missing_field):
        CalidadCodigoAgent().run(intake, provider)


def test_invalid_severity_raises():
    finding = {**VALID_PAYLOAD_WITH_FINDINGS["findings"][0], "severity": "urgentisima"}
    payload = {"findings": [finding], "pending_items": []}
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="spec", text="revisar código del login")

    with pytest.raises(ValueError, match="severity inválida"):
        CalidadCodigoAgent().run(intake, provider)


def test_findings_not_a_list_raises_clear_error():
    payload = {"findings": "sin hallazgos", "pending_items": []}
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="spec", text="revisar código del login")

    with pytest.raises(ValueError, match="findings debe ser una lista"):
        CalidadCodigoAgent().run(intake, provider)


def test_response_wrapped_in_markdown_fence_is_still_parsed():
    provider = FakeProvider(f"```json\n{json.dumps(VALID_PAYLOAD_CLEAN)}\n```")
    intake = Intake(source="spec", text="revisar código del login")

    result = CalidadCodigoAgent().run(intake, provider)
    assert "Sin hallazgos" in result.content


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
    """Simula un LLM con acceso a repo: explora, y además intenta write_file aunque no
    se lo hayan ofrecido — para confirmar que el tool_executor lo rechaza igual."""

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
    provider = ReadOnlyToolProvider(json.dumps(VALID_PAYLOAD_CLEAN))
    intake = Intake(source="spec", text="revisar código del repo de frontend")

    CalidadCodigoAgent().run(intake, provider)

    tool_names = {tool["name"] for tool in provider.received_tools}
    assert tool_names == {"list_files", "read_file"}
    assert provider.write_result.startswith("error:")
    assert (frontend_project / "src" / "login.jsx").exists()  # nunca se tocó el archivo real


def test_falls_back_to_reviewing_only_pasted_code_without_frontend_repo_configured(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    provider = FakeProvider(json.dumps(VALID_PAYLOAD_CLEAN))
    intake = Intake(source="spec", text="revisar código: ```python\nx = 1\n```")

    result = CalidadCodigoAgent().run(intake, provider)

    assert "Sin hallazgos" in result.content


def test_repo_access_failure_is_surfaced_as_pending_item_not_a_crash(tmp_path, monkeypatch):
    qa_project = tmp_path / "qa-project.yaml"
    qa_project.write_text(
        yaml.safe_dump({"repositories": {"frontend": {"url": str(tmp_path / "no-existe"), "branch": "main"}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(repo_access, "_CACHE_ROOT", tmp_path / "cache")
    monkeypatch.chdir(tmp_path)

    provider = FakeProvider(json.dumps(VALID_PAYLOAD_CLEAN))
    intake = Intake(source="spec", text="revisar código del repo de frontend")

    result = CalidadCodigoAgent().run(intake, provider)

    assert "No se pudo usar el repo de frontend" in result.content


class RaisingToolProvider:
    def complete(self, system, messages, tools=None, tool_executor=None, **kwargs):
        raise RuntimeError("el provider explotó a mitad del tool-calling")


def test_tool_calling_failure_falls_back_to_reviewing_without_repo_access(frontend_project):
    intake = Intake(source="spec", text="revisar código del repo de frontend")

    class SequencedProvider:
        def complete(self, system, messages, tools=None, tool_executor=None, **kwargs):
            if tools is not None:
                raise RuntimeError("el provider explotó a mitad del tool-calling")
            return json.dumps(VALID_PAYLOAD_CLEAN)

    result = CalidadCodigoAgent().run(intake, SequencedProvider())

    assert "Sin hallazgos" in result.content
    assert "tool-calling falló" in result.content
