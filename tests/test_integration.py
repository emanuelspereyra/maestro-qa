"""Corre el orquestador con los agentes REALES ya registrados (no fakes aislados).

Objetivo: detectar roturas de integración que los tests por-agente no ven porque cada uno
limpia el AGENT_REGISTRY antes de correr. Cuando se agregue un agente nuevo al fleet,
sumarlo aquí también: una respuesta canned en RoutingFakeProvider y su nombre en el
assert de agentes esperados.
"""

import json

from maestro_qa.agents import automatizacion, casos_manuales  # noqa: F401
from maestro_qa.orchestrator import Intake, run

CASES_RESPONSE = json.dumps(
    [
        {
            "case_id": "FE-TC-001",
            "feature_id": "auth.google_login",
            "layer": "frontend",
            "scenario_family": "happy-path",
            "business_rule_ids": ["BR-AUTH-001"],
            "coverage_dimensions": ["oauth-consent"],
            "title": "Login con Google exitoso",
            "objective": "Verificar el login",
            "sources": ["REQ-001"],
            "work_item_ids": [],
            "confidence": "confirmed",
            "priority": "high",
            "execution_type": "both",
            "preconditions": ["Cuenta de Google válida"],
            "steps": [{"order": 1, "action": "Click en login", "expected": "Redirige a Google"}],
            "expected_result": "Usuario autenticado",
            "actual_result": "Pendiente",
            "status": "NOT_EXECUTED",
            "data_contract": {
                "dataset_id": "DS-AUTH-001",
                "requirements": [],
                "setup_method": "fixture",
                "cleanup_method": "none",
            },
            "evidence_required": ["screenshot"],
        }
    ]
)

AUTOMATIZACION_RESPONSE = json.dumps(
    {
        "page_object_filename": "pages/google_login_page.py",
        "page_object_code": (
            "from pages.base_page import BasePage\n\n\n"
            "class GoogleLoginPage(BasePage):\n"
            "    def click_login(self) -> None:\n"
            "        self.page.get_by_role('button', name='Google').click()\n"
        ),
        "test_filename": "tests/test_google_login.py",
        "test_code": (
            "def test_login(page, base_url):\n"
            "    assert base_url\n"
        ),
        "pending_items": [],
    }
)


class RoutingFakeProvider:
    """Devuelve la respuesta canned que corresponde según qué agente preguntó."""

    def complete(self, system, messages, **kwargs):
        if "page_object_filename" in system:
            return AUTOMATIZACION_RESPONSE
        return CASES_RESPONSE


def test_real_agents_run_together_without_stepping_on_each_other():
    intake = Intake(source="jira_ticket", text="Automatizar con e2e el login con Google")
    result = run(intake, provider=RoutingFakeProvider())

    agents_ran = {r.agent for r in result.results}
    assert "casos_manuales" in agents_ran
    assert "automatizacion" in agents_ran
    assert not any(r.error for r in result.results), result.results


def test_ticket_without_automation_keywords_only_runs_casos_manuales():
    intake = Intake(source="spec", text="Agregar un campo de teléfono al perfil")
    result = run(intake, provider=RoutingFakeProvider())

    agents_ran = {r.agent for r in result.results}
    assert "casos_manuales" in agents_ran
    assert "automatizacion" not in agents_ran
