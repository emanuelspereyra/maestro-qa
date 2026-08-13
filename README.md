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

### 4. Instalar en VS Code con GitHub Copilot

**Confirmado funcionando con VS Code + GitHub Copilot real (Emanuel, 2026-08-13)** — la
configuración de esta sección está probada, no es solo teórica.

**Prerrequisitos:**
- VS Code actualizado (soporte MCP nativo, sin flag experimental que activar).
- Extensiones **GitHub Copilot** y **GitHub Copilot Chat** instaladas y con sesión iniciada.
- Python del entorno donde corriste `pip install -e .` accesible desde la terminal que use
  VS Code (mismo intérprete que usaste en el paso 2).

**Paso a paso:**

1. En la raíz de este repo (o del proyecto donde quieras invocarlo), crear
   `.vscode/mcp.json`:

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

   El `cwd` importa: `config.load_env_file()` busca `.env` relativo a ese directorio, y
   `ensure_project()`/`run_qa` crean `qa-project.yaml`/`qa-history/` ahí mismo. Si vas a
   invocarlo desde otro proyecto, apuntá `cwd` a la carpeta de **este** repo (donde está el
   `.env` con `MAESTRO_API_KEY`), no a la del otro proyecto.

2. VS Code detecta el archivo automáticamente. Si no, abrir la paleta de comandos
   (`Cmd/Ctrl+Shift+P`) → **MCP: List Servers** para confirmar que `maestro-qa` aparece, o
   **MCP: Show Output** si algo falló al arrancar.

3. Abrir Copilot Chat en modo **Agent** (no modo Ask/Edit) — ahí es donde Copilot puede
   invocar tools de servidores MCP. En el selector de herramientas (ícono de herramientas
   en el panel de chat) confirmar que `run_qa` y `ensure_project` aparecen habilitadas.

4. Probarlo pidiéndole algo concreto en el chat, ej.: *"Usá la tool run_qa de maestro-qa
   para generar casos de prueba de: agregar un campo de teléfono al perfil de usuario"*.
   Copilot debería pedir confirmación antes de ejecutar la tool (comportamiento normal de
   Agent mode) y devolver el reporte agregado.

**Si algo no aparece:** revisar `MCP: Show Output` en la paleta de comandos — ahí se ve el
stderr del proceso si `python3 -m maestro_qa.mcp_server` falla al arrancar (por ejemplo, si
falta instalar el paquete en ese intérprete, o si `MAESTRO_API_KEY` no está en el `.env` del
`cwd` configurado).

Si el formato de `.vscode/mcp.json` cambia en una versión futura de la extensión, la
[documentación oficial de GitHub Copilot sobre servidores MCP](https://code.visualstudio.com/docs/copilot/customization/mcp-servers)
tiene la sintaxis vigente.

### Qué está validado y qué no

`tests/test_mcp_server.py` valida el servidor conectándose por stdio con el cliente Python
del propio SDK MCP (`mcp.client`) — arranca el servidor como subproceso, lista las tools,
llama una — sin mockear el protocolo. Eso ya daba confianza de que cualquier cliente MCP
genérico (Claude Code, Copilot) iba a funcionar; la instalación real en VS Code de arriba lo
terminó de confirmar con el cliente real.

## Smoke test (conectividad real)

`pytest` usa providers falsos — no confirma que el adaptador real hable bien con la API del
proveedor. Antes de confiar en un agente nuevo, correr una vez con una key real:

```bash
MAESTRO_PROVIDER=anthropic MAESTRO_MODEL=claude-sonnet-5 MAESTRO_API_KEY=sk-... \
    python scripts/smoke_test.py
```
