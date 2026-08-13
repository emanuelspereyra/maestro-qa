# Maestro QA

Orquestador multi-agente de testing. Recibe una tarea (ticket de Jira o spec/PRD) y
reparte el trabajo entre agentes especializados (casos manuales, automatización, datos de
prueba, priorización de bugs, regresión, performance, seguridad, trazabilidad,
release-readiness). Se expone como servidor MCP — usable desde Claude Code y GitHub Copilot
sin integración adicional.

Ver [`specs/000-arquitectura.md`](specs/000-arquitectura.md) para el diseño completo.

## Metodología: Spec-Driven Development

Ninguna feature se implementa sin una spec primero. Antes de escribir código:

1. Copiá `specs/TEMPLATE.md` a `specs/NNN-nombre-feature.md`.
2. Completala: problema, alcance, diseño, criterios de aceptación.
3. Implementá contra esa spec. El PR referencia el número de spec.

## Desarrollo

```bash
pip install -e ".[dev]"
ruff check .
mypy src
pytest
```

`tests/test_integration.py` corre el orquestador con los agentes YA registrados (no fakes
aislados) — detecta roturas de integración entre agentes reales. Al agregar un agente nuevo,
sumarlo también ahí.

## Servidor MCP

Expone Maestro QA como servidor MCP (ver [`specs/020-servidor-mcp.md`](specs/020-servidor-mcp.md)) — dos tools:

- `run_qa(source, text)` — corre el orquestador sobre un ticket (`source="jira_ticket"`) o
  una spec/PRD (`source="spec"`), rutea a los agentes que apliquen y devuelve el reporte
  agregado, incluyendo el veredicto final de `release_readiness`.
- `ensure_project()` — crea/lee `qa-project.yaml` y reporta qué credenciales propias de
  Maestro QA están configuradas (sin exponer valores).

### 1. Configurar credenciales

```bash
cp .env.example .env
# completar MAESTRO_PROVIDER / MAESTRO_MODEL / MAESTRO_API_KEY como mínimo
```

### 2. Correrlo directo (para probar)

```bash
pip install -e .
python -m maestro_qa.mcp_server
# o, si se instaló el paquete: maestro-qa-mcp
```

Corre por stdio — no hay puerto que abrir, el cliente (Claude Code, Copilot, etc.) lo lanza
como subproceso él mismo.

### 3. Registrarlo en Claude Code

```bash
claude mcp add maestro-qa -- python3 -m maestro_qa.mcp_server
```

O agregando manualmente a `.mcp.json` en la raíz del proyecto donde se vaya a usar:

```json
{
  "mcpServers": {
    "maestro-qa": {
      "command": "python3",
      "args": ["-m", "maestro_qa.mcp_server"],
      "cwd": "/ruta/a/maestro-qa"
    }
  }
}
```

### 4. Registrarlo en VS Code / GitHub Copilot

Copilot en VS Code también habla MCP — la clave exacta del archivo de config puede variar
según la versión de la extensión, revisar la
[documentación oficial de GitHub Copilot sobre servidores MCP](https://code.visualstudio.com/docs/copilot/customization/mcp-servers)
si el formato de abajo no coincide. Como punto de partida (`.vscode/mcp.json`):

```json
{
  "servers": {
    "maestro-qa": {
      "command": "python3",
      "args": ["-m", "maestro_qa.mcp_server"],
      "cwd": "/ruta/a/maestro-qa"
    }
  }
}
```

### Qué está validado y qué no

`tests/test_mcp_server.py` valida el servidor real conectándose por stdio con el cliente
Python del propio SDK MCP (`mcp.client`) — arranca el servidor como subproceso, lista las
tools, llama una — sin mockear el protocolo. Claude Code y Copilot son clientes MCP
genéricos: si el protocolo está bien implementado (vía el SDK oficial), son compatibles sin
necesitar una prueba específica por cliente. Lo que **no** se hizo: abrir VS Code con
Copilot y probarlo a mano — no hay entorno gráfico en este entorno de desarrollo. Confirmarlo
una vez con tu propio VS Code antes de darlo por sentado en producción.

## Smoke test (conectividad real)

`pytest` usa providers falsos — no confirma que el adaptador real hable bien con la API del
proveedor. Antes de confiar en un agente nuevo, correr una vez con una key real:

```bash
MAESTRO_PROVIDER=anthropic MAESTRO_MODEL=claude-sonnet-5 MAESTRO_API_KEY=sk-... \
    python scripts/smoke_test.py
```
