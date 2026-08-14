import httpx
import pytest

from maestro_qa import readers
from maestro_qa.readers.azure_devops import AzureDevOpsReader


def test_get_reader_returns_none_without_maestro_reader_set(monkeypatch):
    monkeypatch.delenv("MAESTRO_READER", raising=False)
    assert readers.get_reader() is None


def test_get_reader_raises_for_unknown_backend(monkeypatch):
    monkeypatch.setenv("MAESTRO_READER", "not-a-real-backend")
    with pytest.raises(ValueError, match="Unknown MAESTRO_READER"):
        readers.get_reader()


def test_get_reader_raises_naming_missing_azure_devops_vars(monkeypatch):
    monkeypatch.setenv("MAESTRO_READER", "azure_devops")
    monkeypatch.delenv("MAESTRO_AZURE_DEVOPS_ORG", raising=False)
    monkeypatch.delenv("MAESTRO_AZURE_DEVOPS_PROJECT", raising=False)
    monkeypatch.delenv("MAESTRO_AZURE_DEVOPS_PAT", raising=False)

    with pytest.raises(ValueError, match="MAESTRO_AZURE_DEVOPS_ORG, MAESTRO_AZURE_DEVOPS_PROJECT, MAESTRO_AZURE_DEVOPS_PAT"):
        readers.get_reader()


def test_get_reader_returns_configured_azure_devops_reader(monkeypatch):
    monkeypatch.setenv("MAESTRO_READER", "Azure_DevOps ")
    monkeypatch.setenv("MAESTRO_AZURE_DEVOPS_ORG", "cda")
    monkeypatch.setenv("MAESTRO_AZURE_DEVOPS_PROJECT", "qa-project")
    monkeypatch.setenv("MAESTRO_AZURE_DEVOPS_PAT", "fake-pat")

    reader = readers.get_reader()

    assert isinstance(reader, AzureDevOpsReader)
    assert reader.org == "cda"
    assert reader.project == "qa-project"


def test_azure_devops_reader_fetches_title_and_strips_html_description(monkeypatch):
    captured = {}

    def fake_get(url, auth, timeout):
        captured["url"] = url
        captured["auth"] = auth
        return httpx.Response(
            200,
            json={
                "fields": {
                    "System.Title": "El login con Google no redirige",
                    "System.Description": "<div><p>Pasos:</p><ol><li>Click en login</li></ol></div>",
                }
            },
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    reader = AzureDevOpsReader(org="cda", project="qa-project", pat="fake-pat")
    ticket = reader.fetch("123")

    assert ticket.external_id == "123"
    assert ticket.title == "El login con Google no redirige"
    assert "Pasos: Click en login" in ticket.text
    assert "<" not in ticket.text
    assert captured["url"].endswith("/_apis/wit/workitems/123?api-version=7.1")
    assert captured["auth"] == ("", "fake-pat")


def test_azure_devops_reader_falls_back_to_repro_steps_when_description_is_empty(monkeypatch):
    monkeypatch.setattr(
        httpx,
        "get",
        lambda url, auth, timeout: httpx.Response(
            200,
            json={"fields": {"System.Title": "Bug de checkout", "Microsoft.VSTS.TCM.ReproSteps": "<p>Repro acá</p>"}},
        ),
    )

    reader = AzureDevOpsReader(org="cda", project="qa-project", pat="fake-pat")
    ticket = reader.fetch("456")

    assert "Repro acá" in ticket.text


def test_azure_devops_reader_uses_placeholder_title_when_missing(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda url, auth, timeout: httpx.Response(200, json={"fields": {}}))

    reader = AzureDevOpsReader(org="cda", project="qa-project", pat="fake-pat")
    ticket = reader.fetch("789")

    assert ticket.title == "Work item 789"
    assert ticket.text == "Work item 789"


def test_azure_devops_reader_raises_clear_error_on_api_failure(monkeypatch):
    monkeypatch.setattr(
        httpx, "get", lambda url, auth, timeout: httpx.Response(404, json={"message": "not found"})
    )
    reader = AzureDevOpsReader(org="cda", project="qa-project", pat="fake-pat")

    with pytest.raises(readers.ReaderError, match="404"):
        reader.fetch("999")
