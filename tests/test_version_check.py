import httpx
import pytest

from maestro_qa import version_check


def test_installed_version_reads_from_package_metadata():
    # no hardcodeamos el número — solo que sea un string no vacío con puntos
    assert "." in version_check.installed_version()


def test_latest_version_returns_none_when_no_releases_exist(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda url, timeout, headers: httpx.Response(404))
    assert version_check.latest_version() is None


def test_latest_version_returns_none_on_network_error(monkeypatch):
    def raise_network_error(url, timeout, headers):
        raise httpx.ConnectError("no network")

    monkeypatch.setattr(httpx, "get", raise_network_error)
    assert version_check.latest_version() is None


def test_latest_version_strips_leading_v(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda url, timeout, headers: httpx.Response(200, json={"tag_name": "v1.2.3"}))
    assert version_check.latest_version() == "1.2.3"


def test_check_for_update_returns_none_when_up_to_date(monkeypatch):
    monkeypatch.setattr(version_check, "installed_version", lambda: "1.0.0")
    monkeypatch.setattr(version_check, "latest_version", lambda: "1.0.0")
    assert version_check.check_for_update() is None


def test_check_for_update_returns_none_when_installed_is_newer_than_latest(monkeypatch):
    # ej. corriendo desde un commit sin release todavía
    monkeypatch.setattr(version_check, "installed_version", lambda: "1.5.0")
    monkeypatch.setattr(version_check, "latest_version", lambda: "1.0.0")
    assert version_check.check_for_update() is None


def test_check_for_update_returns_none_when_latest_is_unavailable(monkeypatch):
    monkeypatch.setattr(version_check, "installed_version", lambda: "1.0.0")
    monkeypatch.setattr(version_check, "latest_version", lambda: None)
    assert version_check.check_for_update() is None


def test_check_for_update_reports_both_versions_when_a_newer_one_exists(monkeypatch):
    monkeypatch.setattr(version_check, "installed_version", lambda: "0.1.0")
    monkeypatch.setattr(version_check, "latest_version", lambda: "0.2.0")

    notice = version_check.check_for_update()

    assert notice is not None
    assert "0.2.0" in notice
    assert "0.1.0" in notice


@pytest.mark.parametrize("malformed", ["not-a-version", "1.0.0-beta"])
def test_check_for_update_returns_none_for_malformed_versions_instead_of_crashing(monkeypatch, malformed):
    monkeypatch.setattr(version_check, "installed_version", lambda: "1.0.0")
    monkeypatch.setattr(version_check, "latest_version", lambda: malformed)
    assert version_check.check_for_update() is None
