# Maestro QA

Orquestador multi-agente de testing. Recibe una tarea (ticket de Jira o spec/PRD) y
reparte el trabajo entre agentes especializados (casos manuales, automatización, datos de
prueba, priorización de bugs, regresión, performance, seguridad, trazabilidad,
release-readiness). Se expone como servidor MCP — usable desde Claude Code, GitHub Copilot
y Codex CLI sin integración adicional (protocolo genérico, confirmado con los 3).

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

**Opción recomendada — sin instalar nada a mano:** si tenés
[`uv`](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`, un
solo binario, no depende de tener el venv ni las dependencias de Python ya instaladas):

```bash
uvx --from /ruta/a/maestro-qa maestro-qa-mcp
```

`uvx` resuelve e instala todas las dependencias en un entorno aislado y efímero la primera
vez que corre (~1-2 segundos, se cachea después) — es la respuesta real a "¿y si la máquina
de otra persona del equipo no tiene nada de esto instalado?": con `uv` presente, no hace
falta nada más. Confirmado funcionando de punta a punta (protocolo MCP real, sin venv
preexistente).

**Opción manual (para desarrollo local, editando el código):**

```bash
pip install -e .
python -m maestro_qa.mcp_server
# o, si se instaló el paquete: maestro-qa-mcp
```

Corre por stdio — no hay puerto que abrir, el cliente (Claude Code, Copilot, Codex, etc.)
lo lanza como subproceso él mismo.

**Ojo con el intérprete si usás la opción manual — bug real que encontramos probando
esto:** si instalaste con `pip install -e .` dentro de un venv (`.venv/`, como en este
repo), un `command: "python3"` genérico en la config del cliente puede resolver al Python
**del sistema**, que no tiene `maestro_qa` instalado — el servidor falla al arrancar y el
cliente reporta errores confusos ("not ready", "connection closed") en vez de "módulo no
encontrado". Usá siempre el path **absoluto** al intérprete del venv (o, más simple,
`uvx` de arriba, que no tiene este problema):

```bash
which python  # con el venv activado — ese es el path a usar, ej. /ruta/a/maestro-qa/.venv/bin/python
```

### 3. Registrarlo en Claude Code

Con `uv` (nada que instalar antes en la máquina de quien lo use):

```bash
claude mcp add maestro-qa -- uvx --from /ruta/a/maestro-qa maestro-qa-mcp
```

O con el venv ya instalado a mano:

```bash
claude mcp add maestro-qa -- /ruta/a/maestro-qa/.venv/bin/python -m maestro_qa.mcp_server
```

O agregando manualmente a `.mcp.json` en la raíz del proyecto donde se vaya a usar:

```json
{
  "mcpServers": {
    "maestro-qa": {
      "command": "uvx",
      "args": ["--from", "/ruta/a/maestro-qa", "maestro-qa-mcp"]
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
- El venv instalado (`pip install -e .`, paso 2) — la config confirmada usa ese Python
  directo. `uv`/`uvx` (misma idea que en Claude Code/Codex) debería funcionar igual acá,
  pero esta sección puntual se probó con el venv, no con `uvx`.

**Paso a paso:**

1. En la raíz de este repo (o del proyecto donde quieras invocarlo), crear
   `.vscode/mcp.json`:

   ```json
   {
     "servers": {
       "maestro-qa": {
         "command": "/ruta/a/maestro-qa/.venv/bin/python",
         "args": ["-m", "maestro_qa.mcp_server"],
         "cwd": "/ruta/a/maestro-qa"
       }
     }
   }
   ```

   Alternativa sin venv preinstalado (no re-confirmada puntualmente en VS Code, mismo
   mecanismo que en Claude Code/Codex):

   ```json
   {
     "servers": {
       "maestro-qa": {
         "command": "uvx",
         "args": ["--from", "/ruta/a/maestro-qa", "maestro-qa-mcp"]
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
stderr del proceso si el servidor falla al arrancar (típicamente: el `command` apunta a un
Python sin `maestro_qa` instalado — ver la nota del paso 2 — o `.env` no está en el `cwd`
configurado).

Si el formato de `.vscode/mcp.json` cambia en una versión futura de la extensión, la
[documentación oficial de GitHub Copilot sobre servidores MCP](https://code.visualstudio.com/docs/copilot/customization/mcp-servers)
tiene la sintaxis vigente.

### 5. Registrarlo en Codex CLI

**Confirmado funcionando con Codex CLI real (`codex-cli 0.146.0`, 2026-08-13)** — se
registró el servidor y se probó `ensure_project` de punta a punta vía `codex exec`, sin
mocks.

Con `uv` (probado — sin venv preinstalado):

```bash
codex mcp add maestro-qa \
  --env MAESTRO_ENV_FILE=/ruta/a/maestro-qa/.env \
  -- uvx --from /ruta/a/maestro-qa maestro-qa-mcp
```

O con el venv ya instalado a mano:

```bash
codex mcp add maestro-qa \
  --env MAESTRO_ENV_FILE=/ruta/a/maestro-qa/.env \
  -- /ruta/a/maestro-qa/.venv/bin/python -m maestro_qa.mcp_server
```

A diferencia de Claude Code/VS Code, `codex mcp add` no tiene una flag `--cwd` — por eso acá
se usa `--env MAESTRO_ENV_FILE=...` en vez de depender del directorio de trabajo para
encontrar `.env` (`config.load_env_file()` respeta esa variable si está seteada, sin
importar desde dónde Codex arranque el proceso). Este mismo patrón con `env` en vez de `cwd`
también funciona en Claude Code/VS Code si se prefiere no fijar un directorio de trabajo.

Verificar:

```bash
codex mcp list        # confirma que "maestro-qa" aparece enabled
codex mcp get maestro-qa
```

Y probarlo de verdad (no necesita `MAESTRO_API_KEY` real, `ensure_project` no llama a
ningún LLM):

```bash
codex exec --sandbox danger-full-access \
  "Usá la tool ensure_project del servidor MCP maestro-qa y decime qué devolvió."
```

`--sandbox danger-full-access` hizo falta porque el servidor arranca un subproceso Python —
con el sandbox por defecto (`read-only`) la conexión al servidor no se establece. Ajustar
según cuánto confíes en lo que corre en tu máquina.

### Qué está validado y qué no

`tests/test_mcp_server.py` valida el servidor conectándose por stdio con el cliente Python
del propio SDK MCP (`mcp.client`) — arranca el servidor como subproceso, lista las tools,
llama una — sin mockear el protocolo. Además de eso, quedó confirmado con los 3 clientes
reales: Claude Code, VS Code + GitHub Copilot, y Codex CLI.

## Smoke test (conectividad real)

`pytest` usa providers falsos — no confirma que el adaptador real hable bien con la API del
proveedor. Antes de confiar en un agente nuevo, correr una vez con una key real:

```bash
MAESTRO_PROVIDER=anthropic MAESTRO_MODEL=claude-sonnet-5 MAESTRO_API_KEY=sk-... \
    python scripts/smoke_test.py
```
