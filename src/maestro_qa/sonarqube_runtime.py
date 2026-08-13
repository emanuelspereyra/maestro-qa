import subprocess
import time
import uuid
from pathlib import Path

import httpx

from . import sonarqube

_DEFAULT_IMAGE = "sonarqube:community"
_DEFAULT_SCANNER_IMAGE = "sonarsource/sonar-scanner-cli:latest"
_DEFAULT_PORT = 9000
_READY_TIMEOUT_SECONDS = 120
_ANALYSIS_TIMEOUT_SECONDS = 300
_POLL_INTERVAL_SECONDS = 3


class SonarQubeRuntimeError(Exception):
    pass


def _docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=check)


def _wait_until_ready(base_url: str) -> None:
    deadline = time.monotonic() + _READY_TIMEOUT_SECONDS
    with httpx.Client() as client:
        while time.monotonic() < deadline:
            try:
                response = client.get(f"{base_url}/api/system/status", timeout=5)
                if response.status_code == 200 and response.json().get("status") == "UP":
                    return
            except httpx.HTTPError:
                pass
            time.sleep(_POLL_INTERVAL_SECONDS)
    raise SonarQubeRuntimeError(f"SonarQube no arrancó dentro de {_READY_TIMEOUT_SECONDS}s")


def _bootstrap_admin(base_url: str, new_password: str) -> None:
    # ponytail: asume admin/admin de una instancia recién creada (contenedor efímero,
    # sin volumen persistente). Si ya fue cambiado antes, esto falla y se ignora.
    with httpx.Client() as client:
        client.post(
            f"{base_url}/api/users/change_password",
            params={"login": "admin", "previousPassword": "admin", "password": new_password},
            auth=("admin", "admin"),
        )


def _create_project(base_url: str, auth: tuple[str, str], project_key: str) -> None:
    with httpx.Client() as client:
        response = client.post(
            f"{base_url}/api/projects/create",
            params={"project": project_key, "name": project_key},
            auth=auth,
        )
    if response.status_code >= 400 and "already exists" not in response.text:
        raise SonarQubeRuntimeError(f"No se pudo crear el proyecto en SonarQube: {response.text}")


def _generate_token(base_url: str, auth: tuple[str, str], token_name: str) -> str:
    with httpx.Client() as client:
        response = client.post(
            f"{base_url}/api/user_tokens/generate",
            params={"name": token_name},
            auth=auth,
        )
    if response.status_code >= 400:
        raise SonarQubeRuntimeError(f"No se pudo generar el token de SonarQube: {response.text}")
    return str(response.json()["token"])


def _run_scanner(repo_path: Path, base_url: str, project_key: str, token: str) -> str:
    container_name = f"maestro-qa-scanner-{uuid.uuid4().hex[:8]}"
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--name",
            container_name,
            "--network",
            "host",
            "-v",
            f"{repo_path}:/usr/src",
            _DEFAULT_SCANNER_IMAGE,
            f"-Dsonar.projectKey={project_key}",
            "-Dsonar.sources=.",
            f"-Dsonar.host.url={base_url}",
            f"-Dsonar.token={token}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SonarQubeRuntimeError(f"sonar-scanner falló: {result.stdout}\n{result.stderr}")

    report_task = repo_path / ".scannerwork" / "report-task.txt"
    if not report_task.exists():
        raise SonarQubeRuntimeError("sonar-scanner no generó report-task.txt")
    for line in report_task.read_text(encoding="utf-8").splitlines():
        if line.startswith("ceTaskId="):
            return line.split("=", 1)[1]
    raise SonarQubeRuntimeError("report-task.txt no contiene ceTaskId")


def _wait_for_analysis(base_url: str, auth: tuple[str, str], task_id: str) -> None:
    deadline = time.monotonic() + _ANALYSIS_TIMEOUT_SECONDS
    with httpx.Client() as client:
        while time.monotonic() < deadline:
            response = client.get(f"{base_url}/api/ce/task", params={"id": task_id}, auth=auth)
            if response.status_code >= 400:
                raise SonarQubeRuntimeError(f"No se pudo consultar el análisis: {response.text}")
            status = response.json()["task"]["status"]
            if status == "SUCCESS":
                return
            if status in {"FAILED", "CANCELED"}:
                raise SonarQubeRuntimeError(f"El análisis de SonarQube terminó en estado {status}")
            time.sleep(_POLL_INTERVAL_SECONDS)
    raise SonarQubeRuntimeError(f"Timeout esperando el análisis de SonarQube ({_ANALYSIS_TIMEOUT_SECONDS}s)")


def run_ephemeral_scan(
    repo_path: Path,
    project_key: str,
    port: int = _DEFAULT_PORT,
    image: str = _DEFAULT_IMAGE,
) -> dict[str, list[dict[str, object]]]:
    """Levanta SonarQube en Docker, escanea repo_path, lee hallazgos y SIEMPRE mata el
    contenedor al final — ver specs/015-sonarqube-efimero.md, no validado contra un
    servidor real todavía."""
    container_name = f"maestro-qa-sonarqube-{uuid.uuid4().hex[:8]}"
    base_url = f"http://localhost:{port}"
    admin_password = uuid.uuid4().hex
    auth = ("admin", admin_password)

    _docker("run", "-d", "--name", container_name, "-p", f"{port}:9000", image)
    try:
        _wait_until_ready(base_url)
        _bootstrap_admin(base_url, admin_password)
        _create_project(base_url, auth, project_key)
        token = _generate_token(base_url, auth, f"scan-{uuid.uuid4().hex[:8]}")
        task_id = _run_scanner(repo_path, base_url, project_key, token)
        _wait_for_analysis(base_url, auth, task_id)
        return sonarqube.fetch_findings(base_url, token, project_key)
    finally:
        _docker("stop", container_name, check=False)
        _docker("rm", container_name, check=False)
