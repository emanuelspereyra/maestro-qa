import httpx
import pytest

from maestro_qa import writers
from maestro_qa.writers.azure_devops import AzureDevOpsWriter
from maestro_qa.writers.base import WorkItem


def test_get_writer_returns_none_without_maestro_writer_set(monkeypatch):
    monkeypatch.delenv("MAESTRO_WRITER", raising=False)
    assert writers.get_writer() is None


def test_get_writer_raises_for_unknown_backend(monkeypatch):
    monkeypatch.setenv("MAESTRO_WRITER", "not-a-real-backend")
    with pytest.raises(ValueError, match="Unknown MAESTRO_WRITER"):
        writers.get_writer()


def test_get_writer_raises_naming_missing_azure_devops_vars(monkeypatch):
    monkeypatch.setenv("MAESTRO_WRITER", "azure_devops")
    monkeypatch.delenv("MAESTRO_AZURE_DEVOPS_ORG", raising=False)
    monkeypatch.delenv("MAESTRO_AZURE_DEVOPS_PROJECT", raising=False)
    monkeypatch.delenv("MAESTRO_AZURE_DEVOPS_PAT", raising=False)

    with pytest.raises(ValueError, match="MAESTRO_AZURE_DEVOPS_ORG, MAESTRO_AZURE_DEVOPS_PROJECT, MAESTRO_AZURE_DEVOPS_PAT"):
        writers.get_writer()


def test_get_writer_returns_configured_azure_devops_writer(monkeypatch):
    monkeypatch.setenv("MAESTRO_WRITER", "Azure_DevOps ")  # normalización de case/espacios
    monkeypatch.setenv("MAESTRO_AZURE_DEVOPS_ORG", "cda")
    monkeypatch.setenv("MAESTRO_AZURE_DEVOPS_PROJECT", "qa-project")
    monkeypatch.setenv("MAESTRO_AZURE_DEVOPS_PAT", "fake-pat")
    monkeypatch.delenv("MAESTRO_AZURE_DEVOPS_WORK_ITEM_TYPE", raising=False)

    writer = writers.get_writer()

    assert isinstance(writer, AzureDevOpsWriter)
    assert writer.org == "cda"
    assert writer.project == "qa-project"
    assert writer.work_item_type == "Task"


def test_azure_devops_writer_builds_correct_request_and_parses_result(monkeypatch):
    captured = {}

    def fake_post(url, auth, headers, json, timeout):
        captured["url"] = url
        captured["auth"] = auth
        captured["headers"] = headers
        captured["json"] = json
        return httpx.Response(
            200,
            json={"id": 42, "_links": {"html": {"href": "https://dev.azure.com/cda/qa/_workitems/edit/42"}}},
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    writer = AzureDevOpsWriter(org="cda", project="qa-project", pat="fake-pat", work_item_type="Test Case")
    result = writer.create(WorkItem(external_ref="FE-TC-001", title="Login válido", description="<p>...</p>"))

    assert result.external_id == "42"
    assert result.url == "https://dev.azure.com/cda/qa/_workitems/edit/42"
    assert "$Test Case" in captured["url"]
    assert captured["auth"] == ("", "fake-pat")
    assert captured["headers"]["Content-Type"] == "application/json-patch+json"
    assert {"op": "add", "path": "/fields/System.Title", "value": "Login válido"} in captured["json"]


def test_azure_devops_writer_raises_clear_error_on_api_failure(monkeypatch):
    monkeypatch.setattr(
        httpx, "post", lambda url, auth, headers, json, timeout: httpx.Response(401, json={"message": "denied"})
    )
    writer = AzureDevOpsWriter(org="cda", project="qa-project", pat="bad-pat")

    with pytest.raises(writers.WriterError, match="401"):
        writer.create(WorkItem(external_ref="FE-TC-001", title="x", description="y"))


def test_azure_devops_writer_raises_clear_error_on_unexpected_response_shape(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda url, auth, headers, json, timeout: httpx.Response(200, json={}))
    writer = AzureDevOpsWriter(org="cda", project="qa-project", pat="pat")

    with pytest.raises(writers.WriterError, match="Respuesta inesperada"):
        writer.create(WorkItem(external_ref="FE-TC-001", title="x", description="y"))
