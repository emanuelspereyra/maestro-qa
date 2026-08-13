import httpx
import pytest

from maestro_qa import sonarqube


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=None)


class FakeClient:
    def __init__(self, issues_payload: dict, hotspots_payload: dict):
        self._issues_payload = issues_payload
        self._hotspots_payload = hotspots_payload
        self.requests: list[tuple[str, dict]] = []

    def get(self, path: str, params: dict) -> FakeResponse:
        self.requests.append((path, params))
        if path == "/api/issues/search":
            return FakeResponse(self._issues_payload)
        return FakeResponse(self._hotspots_payload)


def test_fetch_findings_simplifies_issues_and_hotspots():
    client = FakeClient(
        issues_payload={
            "issues": [
                {"severity": "CRITICAL", "message": "SQL injection", "component": "api:src/db.py", "line": 42}
            ]
        },
        hotspots_payload={
            "hotspots": [
                {
                    "vulnerabilityProbability": "HIGH",
                    "message": "Hardcoded credential",
                    "component": "api:src/auth.py",
                    "line": 10,
                }
            ]
        },
    )

    findings = sonarqube.fetch_findings("https://sonar.example.test", "token123", "my-project", client=client)

    assert findings["vulnerabilities"] == [
        {"severity": "CRITICAL", "message": "SQL injection", "component": "api:src/db.py", "line": 42}
    ]
    assert findings["hotspots"] == [
        {"probability": "HIGH", "message": "Hardcoded credential", "component": "api:src/auth.py", "line": 10}
    ]
    assert client.requests[0][1]["componentKeys"] == "my-project"


def test_fetch_findings_raises_sonarqube_error_on_http_failure():
    client = FakeClient(issues_payload={}, hotspots_payload={})
    client.get = lambda path, params: FakeResponse({}, status_code=500)

    with pytest.raises(sonarqube.SonarQubeError):
        sonarqube.fetch_findings("https://sonar.example.test", "token123", "my-project", client=client)
