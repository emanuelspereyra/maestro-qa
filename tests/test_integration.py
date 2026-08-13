"""Corre el orquestador con los agentes REALES ya registrados (no fakes aislados).

Objetivo: detectar roturas de integración que los tests por-agente no ven porque cada uno
limpia el AGENT_REGISTRY antes de correr. Cuando se agregue un agente nuevo al fleet,
sumarlo aquí también: una respuesta canned en RoutingFakeProvider y su nombre en el
assert de agentes esperados.
"""

import json

from maestro_qa.agents import (  # noqa: F401
    automatizacion,
    automatizacion_api,
    casos_manuales,
    datos_prueba,
    documentacion,
    performance,
    priorizacion_bugs,
    regresion,
    seguridad,
    trazabilidad,
)
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


DATOS_PRUEBA_RESPONSE = json.dumps(
    {
        "dataset_id": "DS-USERS-001",
        "seed": 12345,
        "entities": [
            {
                "name": "users",
                "target": "dbo.users",
                "identifier_fields": ["id"],
                "display_fields": ["username"],
                "sensitive_fields": [],
                "count": 2,
                "fields": {"id": {"type": "uuid"}, "username": {"type": "username"}},
            }
        ],
    }
)


PERFORMANCE_RESPONSE = json.dumps(
    {
        "test_type": "load",
        "locustfile_filename": "performance/locustfile_login.py",
        "locustfile_code": (
            "from locust import HttpUser, task\n\n\n"
            "class LoginUser(HttpUser):\n"
            "    @task\n"
            "    def login(self):\n"
            "        self.client.post('/login', json={})\n"
        ),
        "run_command": "locust -f performance/locustfile_login.py --headless -u 10 -r 1 -t 1m",
        "pending_items": [],
    }
)


PRIORIZACION_BUGS_RESPONSE = json.dumps(
    {
        "title": "El login con Google no redirige",
        "case_id_o_fuente": "FE-TC-001",
        "ambiente_y_versiones": "QA, commit abc123",
        "preconditions": ["Cuenta de Google válida"],
        "datos_usados": "DS-AUTH-001",
        "steps": ["Click en login con Google"],
        "expected_result": "Redirige al dashboard",
        "actual_result": "Se queda en login",
        "reproducibility": "siempre",
        "severity": "High",
        "business_priority": "pendiente de decisión de negocio",
        "evidence_required": ["screenshot"],
    }
)


AUTOMATIZACION_API_RESPONSE = json.dumps(
    {
        "api_client_filename": "clients/users_client.py",
        "api_client_code": (
            "import httpx\n\n\n"
            "class UsersClient:\n"
            "    def __init__(self, api_base_url):\n"
            "        self._client = httpx.Client(base_url=api_base_url)\n"
        ),
        "test_filename": "tests/test_users_api.py",
        "test_code": "def test_create_user(api_base_url):\n    assert api_base_url\n",
        "pending_items": [],
    }
)


SEGURIDAD_RESPONSE = json.dumps(
    {
        "cases": [
            {
                "category": "broken-access-control",
                "title": "Un usuario no puede leer el perfil de otro",
                "objective": "Verificar autorización a nivel de objeto",
                "steps": ["Loguearse como A", "Solicitar GET /users/<id-de-B>"],
                "expected_result": "La API responde 403",
                "severity_if_fails": "High",
            }
        ],
        "pending_items": [],
    }
)


DOCUMENTACION_RESPONSE = json.dumps(
    {
        "doc_type": "user_guide",
        "title": "Iniciar sesión con Google",
        "summary": "Los usuarios pueden loguearse con su cuenta de Google.",
        "sections": [{"heading": "Cómo usarlo", "content": "Click en el botón de Google en el login."}],
        "pending_items": [],
    }
)


REGRESION_RESPONSE = json.dumps(
    {
        "changed_areas": ["endpoint de login"],
        "affected_cases": [{"case_id": "FE-TC-001", "reason": "cubre el login que cambió"}],
        "coverage_gaps": [],
        "regression_priority": "targeted",
        "pending_items": [],
    }
)


TRAZABILIDAD_RESPONSE = json.dumps(
    {
        "acceptance_criteria": [{"id": "AC-1", "text": "El usuario puede loguearse con Google"}],
        "traceability_matrix": [{"criterion_id": "AC-1", "case_ids": ["FE-TC-001"], "status": "covered"}],
        "untraceable_cases": [],
        "pending_items": [],
    }
)


class RoutingFakeProvider:
    """Devuelve la respuesta canned que corresponde según qué agente preguntó."""

    def complete(self, system, messages, **kwargs):
        if "page_object_filename" in system:
            return AUTOMATIZACION_RESPONSE
        if "sensitive_fields" in system:
            return DATOS_PRUEBA_RESPONSE
        if "locustfile_filename" in system:
            return PERFORMANCE_RESPONSE
        if "case_id_o_fuente" in system:
            return PRIORIZACION_BUGS_RESPONSE
        if "api_client_filename" in system:
            return AUTOMATIZACION_API_RESPONSE
        if "severity_if_fails" in system:
            return SEGURIDAD_RESPONSE
        if "doc_type" in system:
            return DOCUMENTACION_RESPONSE
        if "changed_areas" in system:
            return REGRESION_RESPONSE
        if "traceability_matrix" in system:
            return TRAZABILIDAD_RESPONSE
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


def test_datos_prueba_runs_alongside_casos_manuales(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    intake = Intake(source="jira_ticket", text="Necesito un dataset de usuarios de prueba")
    result = run(intake, provider=RoutingFakeProvider())

    agents_ran = {r.agent for r in result.results}
    assert "casos_manuales" in agents_ran
    assert "datos_prueba" in agents_ran
    assert not any(r.error for r in result.results), result.results


def test_performance_runs_alongside_casos_manuales():
    intake = Intake(source="jira_ticket", text="Necesitamos probar la carga y el throughput del login")
    result = run(intake, provider=RoutingFakeProvider())

    agents_ran = {r.agent for r in result.results}
    assert "casos_manuales" in agents_ran
    assert "performance" in agents_ran
    assert not any(r.error for r in result.results), result.results


def test_priorizacion_bugs_runs_alongside_casos_manuales():
    intake = Intake(source="jira_ticket", text="Reportar el bug del login que no redirige")
    result = run(intake, provider=RoutingFakeProvider())

    agents_ran = {r.agent for r in result.results}
    assert "casos_manuales" in agents_ran
    assert "priorizacion_bugs" in agents_ran
    assert not any(r.error for r in result.results), result.results


def test_automatizacion_api_runs_alongside_casos_manuales():
    intake = Intake(source="jira_ticket", text="Automatizar el endpoint backend de creación de usuarios")
    result = run(intake, provider=RoutingFakeProvider())

    agents_ran = {r.agent for r in result.results}
    assert "casos_manuales" in agents_ran
    assert "automatizacion_api" in agents_ran
    assert not any(r.error for r in result.results), result.results


def test_seguridad_runs_alongside_casos_manuales():
    intake = Intake(source="jira_ticket", text="Revisar permisos y autorización para ver el perfil de otro usuario")
    result = run(intake, provider=RoutingFakeProvider())

    agents_ran = {r.agent for r in result.results}
    assert "casos_manuales" in agents_ran
    assert "seguridad" in agents_ran
    assert not any(r.error for r in result.results), result.results


def test_documentacion_runs_alongside_casos_manuales():
    intake = Intake(source="jira_ticket", text="Documentar el login con Google para el manual de usuario")
    result = run(intake, provider=RoutingFakeProvider())

    agents_ran = {r.agent for r in result.results}
    assert "casos_manuales" in agents_ran
    assert "documentacion" in agents_ran
    assert not any(r.error for r in result.results), result.results


def test_regresion_runs_alongside_casos_manuales():
    intake = Intake(source="jira_ticket", text="Se modificó el endpoint de login, correr la regresión")
    result = run(intake, provider=RoutingFakeProvider())

    agents_ran = {r.agent for r in result.results}
    assert "casos_manuales" in agents_ran
    assert "regresion" in agents_ran
    assert not any(r.error for r in result.results), result.results


def test_trazabilidad_runs_by_default_on_every_ticket():
    intake = Intake(source="spec", text="Agregar un campo de teléfono al perfil")
    result = run(intake, provider=RoutingFakeProvider())

    agents_ran = {r.agent for r in result.results}
    assert "casos_manuales" in agents_ran
    assert "trazabilidad" in agents_ran
    assert not any(r.error for r in result.results), result.results


class RecordingRoutingFakeProvider(RoutingFakeProvider):
    """Igual que RoutingFakeProvider, pero guarda cada mensaje recibido por agente."""

    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    def complete(self, system, messages, **kwargs):
        self.calls.append((system, messages[0]["content"]))
        return super().complete(system, messages, **kwargs)


def test_datos_prueba_receives_the_dataset_id_from_casos_manuales(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    provider = RecordingRoutingFakeProvider()
    intake = Intake(source="jira_ticket", text="Necesito un dataset de usuarios de prueba")

    run(intake, provider=provider)

    datos_prueba_message = next(text for system, text in provider.calls if "sensitive_fields" in system)
    assert "DS-AUTH-001" in datos_prueba_message
    assert "Casos de prueba ya generados" in datos_prueba_message
