import json

import pytest

from maestro_qa.agents.performance import AGENT_REGISTRY, PerformanceAgent
from maestro_qa.orchestrator import Intake

VALID_PAYLOAD = {
    "test_type": "load",
    "locustfile_filename": "performance/locustfile_checkout.py",
    "locustfile_code": (
        "from locust import HttpUser, task, between\n\n"
        "from qa_environment import resolve_setting, target_environment\n\n\n"
        "class CheckoutUser(HttpUser):\n"
        "    wait_time = between(1, 3)\n"
        "    host = resolve_setting('API_BASE_URL', target_environment())\n\n"
        "    @task\n"
        "    def checkout(self):\n"
        "        self.client.post('/checkout', json={})\n"
    ),
    "run_command": "locust -f performance/locustfile_checkout.py --headless -u 50 -r 5 -t 5m",
    "pending_items": [],
}


class FakeProvider:
    def __init__(self, response: str):
        self._response = response

    def complete(self, system, messages, **kwargs):
        return self._response


def test_registers_itself():
    assert isinstance(AGENT_REGISTRY["performance"], PerformanceAgent)


def test_valid_locustfile_returns_content_with_type_and_command():
    provider = FakeProvider(json.dumps(VALID_PAYLOAD))
    intake = Intake(source="jira_ticket", text="probar carga del checkout con 50 usuarios")

    result = PerformanceAgent().run(intake, provider)

    assert result.agent == "performance"
    assert "Tipo de ensayo: load" in result.content
    assert "class CheckoutUser(HttpUser)" in result.content
    assert "locust -f performance/locustfile_checkout.py" in result.content


def test_pending_nfrs_are_surfaced_not_invented():
    payload = {**VALID_PAYLOAD, "pending_items": ["Falta el SLA de p95 esperado"]}
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="spec", text="necesitamos un test de carga")

    result = PerformanceAgent().run(intake, provider)

    assert "Falta el SLA de p95 esperado" in result.content


def test_invalid_python_syntax_raises():
    payload = {**VALID_PAYLOAD, "locustfile_code": "class Broken(:\n    pass"}
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="spec", text="probar carga del checkout")

    with pytest.raises(ValueError, match="locustfile_checkout.py"):
        PerformanceAgent().run(intake, provider)


def test_response_wrapped_in_markdown_fence_is_still_parsed():
    provider = FakeProvider(f"```json\n{json.dumps(VALID_PAYLOAD)}\n```")
    intake = Intake(source="spec", text="probar carga del checkout")

    result = PerformanceAgent().run(intake, provider)
    assert "CheckoutUser" in result.content
