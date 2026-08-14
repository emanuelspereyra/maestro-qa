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


@pytest.mark.parametrize(
    "missing_field", ["test_type", "locustfile_filename", "locustfile_code", "run_command"]
)
def test_missing_required_field_raises_clear_error_not_keyerror(missing_field):
    payload = dict(VALID_PAYLOAD)
    del payload[missing_field]
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="spec", text="probar carga del checkout")

    with pytest.raises(ValueError, match=missing_field):
        PerformanceAgent().run(intake, provider)


def test_invalid_test_type_raises():
    payload = {**VALID_PAYLOAD, "test_type": "smoke"}  # "smoke" no es un tipo válido acá
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="spec", text="probar carga del checkout")

    with pytest.raises(ValueError, match="test_type inválido"):
        PerformanceAgent().run(intake, provider)


def test_test_type_with_different_casing_is_normalized_not_rejected():
    # bug real (spec 022): el LLM puede devolver "Load" en vez de "load" pese al system
    # prompt en minúsculas; antes esto rompía con "test_type inválido".
    payload = {**VALID_PAYLOAD, "test_type": "Load"}
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="spec", text="probar carga del checkout")

    result = PerformanceAgent().run(intake, provider)

    assert "Tipo de ensayo: load" in result.content


def test_non_string_locustfile_code_raises_clear_error_not_typeerror():
    # bug real (auditoría 2026-08-14): ast.parse(payload["locustfile_code"]) sin chequeo
    # de tipo tiraba TypeError sin capturar si el LLM devolvía algo que no fuera string.
    payload = {**VALID_PAYLOAD, "locustfile_code": ["from locust import HttpUser"]}
    provider = FakeProvider(json.dumps(payload))
    intake = Intake(source="spec", text="probar carga del checkout")

    with pytest.raises(ValueError, match="se esperaba código como string"):
        PerformanceAgent().run(intake, provider)
