"""Tests del servidor MCP: lógica de las tools con providers fake (unit), y una
verificación real de protocolo conectándose por stdio con el cliente del SDK MCP a un
subproceso real del servidor — no arranca Claude Code ni VS Code, valida que el
servidor implementa bien el protocolo (ver specs/020-servidor-mcp.md).
"""

import asyncio
import json
import sys

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from maestro_qa import mcp_server

CASES_RESPONSE = json.dumps(
    [
        {
            "case_id": "FE-TC-001",
            "feature_id": "profile.phone",
            "layer": "frontend",
            "scenario_family": "happy-path",
            "business_rule_ids": ["BR-PROFILE-001"],
            "coverage_dimensions": ["valid-data"],
            "title": "Agregar teléfono válido",
            "objective": "Verificar que se puede agregar un teléfono",
            "sources": ["REQ-001"],
            "work_item_ids": [],
            "confidence": "confirmed",
            "priority": "medium",
            "execution_type": "manual",
            "preconditions": ["Perfil existente"],
            "steps": [{"order": 1, "action": "Completar el teléfono", "expected": "Se guarda"}],
            "expected_result": "El teléfono queda guardado",
            "actual_result": "Pendiente",
            "status": "NOT_EXECUTED",
            "data_contract": {
                "dataset_id": "DS-PROFILE-001",
                "requirements": [],
                "setup_method": "fixture",
                "cleanup_method": "none",
            },
            "evidence_required": ["screenshot"],
        }
    ]
)

TRAZABILIDAD_RESPONSE = json.dumps(
    {
        "acceptance_criteria": [{"id": "AC-1", "text": "El usuario puede agregar un teléfono"}],
        "traceability_matrix": [{"criterion_id": "AC-1", "case_ids": ["FE-TC-001"], "status": "covered"}],
        "untraceable_cases": [],
        "pending_items": [],
    }
)

RELEASE_READINESS_RESPONSE = json.dumps(
    {
        "overall_status": "GO",
        "summary": "Sin errores.",
        "blocking_issues": [],
        "non_blocking_notes": [],
    }
)


class FakeProvider:
    def complete(self, system, messages, **kwargs):
        if "traceability_matrix" in system:
            return TRAZABILIDAD_RESPONSE
        if "blocking_issues" in system:
            return RELEASE_READINESS_RESPONSE
        return CASES_RESPONSE


def test_run_qa_runs_real_registered_agents_end_to_end(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(mcp_server, "get_provider", lambda: FakeProvider())
    monkeypatch.setattr(mcp_server.config, "load_env_file", lambda: None)

    result = mcp_server._run_qa_impl("spec", "Agregar un campo de teléfono al perfil")

    assert "casos_manuales" in result
    assert "trazabilidad" in result
    assert "release_readiness" in result


def test_ensure_project_impl_creates_qa_project_yaml(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = mcp_server._ensure_project_impl()

    assert "qa-project.yaml" in result
    assert (tmp_path / "qa-project.yaml").exists()


@pytest.mark.skipif(sys.platform == "win32", reason="stdio subprocess, no aplica en Windows")
def test_server_exposes_tools_over_real_mcp_protocol(tmp_path):
    async def _check() -> None:
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "maestro_qa.mcp_server"],
            cwd=str(tmp_path),
        )
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = {tool.name for tool in tools.tools}
            assert names == {"run_qa", "ensure_project"}

            result = await session.call_tool("ensure_project", {})
            assert not result.is_error
            assert (tmp_path / "qa-project.yaml").exists()

    asyncio.run(_check())
