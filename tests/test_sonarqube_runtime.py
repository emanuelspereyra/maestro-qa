"""Prueba la orquestación (orden, cleanup garantizado) con todo mockeado — nunca levanta
Docker real. Ver specs/015-sonarqube-efimero.md: esto no reemplaza probarlo de verdad.
"""

from pathlib import Path

import pytest

from maestro_qa import sonarqube_runtime


def _patch_happy_path(monkeypatch, calls):
    monkeypatch.setattr(
        sonarqube_runtime, "_docker", lambda *a, **kw: calls.append(("docker", a)) or None
    )
    monkeypatch.setattr(
        sonarqube_runtime, "_wait_until_ready", lambda base_url: calls.append(("ready", base_url))
    )
    monkeypatch.setattr(
        sonarqube_runtime,
        "_bootstrap_admin",
        lambda base_url, password: calls.append(("bootstrap", base_url)),
    )
    monkeypatch.setattr(
        sonarqube_runtime,
        "_create_project",
        lambda base_url, auth, project_key: calls.append(("create_project", project_key)),
    )
    monkeypatch.setattr(
        sonarqube_runtime,
        "_generate_token",
        lambda base_url, auth, token_name: calls.append(("token", token_name)) or "fake-token",
    )
    monkeypatch.setattr(
        sonarqube_runtime,
        "_run_scanner",
        lambda repo_path, base_url, project_key, token: calls.append(("scan", str(repo_path))) or "task-1",
    )
    monkeypatch.setattr(
        sonarqube_runtime, "_wait_for_analysis", lambda base_url, auth, task_id: calls.append(("wait", task_id))
    )
    monkeypatch.setattr(
        sonarqube_runtime.sonarqube,
        "fetch_findings",
        lambda base_url, token, project_key: calls.append(("fetch", project_key))
        or {"vulnerabilities": [], "hotspots": []},
    )


def test_happy_path_follows_expected_order_and_cleans_up(monkeypatch):
    calls = []
    _patch_happy_path(monkeypatch, calls)

    findings = sonarqube_runtime.run_ephemeral_scan(Path("/tmp/some-repo"), "demo-project")

    assert findings == {"vulnerabilities": [], "hotspots": []}
    steps = [c[0] for c in calls]
    assert steps == [
        "docker",  # run -d
        "ready",
        "bootstrap",
        "create_project",
        "token",
        "scan",
        "wait",
        "fetch",
        "docker",  # stop
        "docker",  # rm
    ]


def test_container_is_stopped_and_removed_even_if_scan_fails(monkeypatch):
    calls = []
    _patch_happy_path(monkeypatch, calls)

    def failing_scanner(*args, **kwargs):
        raise sonarqube_runtime.SonarQubeRuntimeError("sonar-scanner explotó")

    monkeypatch.setattr(sonarqube_runtime, "_run_scanner", failing_scanner)

    with pytest.raises(sonarqube_runtime.SonarQubeRuntimeError):
        sonarqube_runtime.run_ephemeral_scan(Path("/tmp/some-repo"), "demo-project")

    docker_calls = [c for c in calls if c[0] == "docker"]
    assert len(docker_calls) == 3  # run, stop, rm — cleanup corrió igual


def test_container_is_stopped_and_removed_even_if_ready_check_fails(monkeypatch):
    calls = []
    _patch_happy_path(monkeypatch, calls)

    def failing_ready(base_url):
        raise sonarqube_runtime.SonarQubeRuntimeError("nunca arrancó")

    monkeypatch.setattr(sonarqube_runtime, "_wait_until_ready", failing_ready)

    with pytest.raises(sonarqube_runtime.SonarQubeRuntimeError):
        sonarqube_runtime.run_ephemeral_scan(Path("/tmp/some-repo"), "demo-project")

    docker_calls = [c for c in calls if c[0] == "docker"]
    assert len(docker_calls) == 3
