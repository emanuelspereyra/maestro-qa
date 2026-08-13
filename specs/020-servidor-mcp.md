# 020 — Servidor MCP

## Problema
Es el requisito de arquitectura original del proyecto (spec 000): un solo servidor cubre
Claude Code y GitHub Copilot de fábrica, porque ambos hablan MCP nativamente. Hasta ahora
`orchestrator.run()` solo se invocaba desde tests y scripts — falta la capa que lo expone
como servidor real.

## Alcance
Cubre CDA-62/63/64/65 (epic "Servidor MCP", CDA-61):
- `mcp_server.py`: dos tools — `run_qa` (corre el orquestador sobre un ticket/spec) y
  `ensure_project` (onboarding, spec 009).
- Transporte stdio (estándar para servidores locales que Claude Code/Copilot lanzan ellos
  mismos como subproceso).
- Historial siempre activo (`qa-history/` en el directorio desde donde se corre el
  servidor) — a diferencia de los tests, acá es el uso real, tiene sentido que quede
  rastro por default.
- Validación de protocolo MCP con el propio SDK (`mcp` package) como cliente, en un test
  automatizado — no arrancando Claude Code o VS Code de verdad dentro de esta sesión.
- Documentación de instalación para Claude Code y Copilot en el README.

**Qué significa "validar compatibilidad" acá, y qué no:** Claude Code y Copilot son ambos
clientes MCP genéricos — si el servidor implementa el protocolo correctamente (vía
`FastMCP`, que ya maneja el wire format), es compatible con cualquier cliente que hable MCP,
sin necesitar una prueba específica por cliente. Lo que se valida es que el servidor arranca,
expone sus tools con el schema correcto, y responde bien a una llamada real — con el cliente
Python del propio SDK MCP, que habla el mismo protocolo que Claude Code/Copilot. **No** se
abrió VS Code con Copilot dentro de esta sesión — no hay entorno gráfico ni la extensión
instalada acá. Queda como verificación manual del lado de Emanuel (instrucciones en el
README).

**Fuera de esta spec:**
- Exponer los agentes vendorizados/backlog (Xray/Jira/Trello writers) como tools — se
  agregan cuando existan.
- Autenticación/autorización del servidor — un servidor MCP local vía stdio hereda el
  entorno del proceso que lo lanza, no hay superficie de red que proteger todavía.
- API REST para plataformas sin MCP (ChatGPT, Kimi, Qwen, DeepSeek) — sigue en backlog
  desde la decisión original (spec 000).

## Diseño

**Por qué FastMCP y no implementar el protocolo a mano:** el paquete `mcp` (SDK oficial)
ya resuelve JSON-RPC, streams, negociación de capacidades y generación de schema desde
type hints de Python — reimplementarlo sería la misma duplicación que ya evitamos con
`validate_cases.py`/`generate_dataset.py` del bundle.

**Separación lógica/decorador:** la lógica de cada tool vive en una función `_*_impl()`
testeable directamente; la función decorada con `@mcp.tool()` es un wrapper de una línea.
Así los tests no dependen de cómo FastMCP envuelve la función.

**`run_qa(source, text)`:** carga `.env` propio de Maestro QA (`config.load_env_file()`),
construye el provider real (`get_provider()`, spec 001) y corre `orchestrator.run()` con
`history_dir="qa-history"` siempre — a diferencia de los tests (que son opt-in a propósito,
spec 006), un servidor real corriendo para CDA debe dejar rastro por default.

**`ensure_project()`:** wrapea `onboarding.ensure_project()` (spec 009) y devuelve un
resumen legible — nunca expone valores de variables, solo si están configuradas.

## Criterios de aceptación
- El servidor expone exactamente 2 tools (`run_qa`, `ensure_project`) con schema correcto,
  verificado con el cliente Python del SDK MCP conectándose por stdio a un subproceso real
  del servidor.
- `run_qa` con un provider fake (inyectado vía monkeypatch de `get_provider`) corre los
  agentes reales ya registrados y devuelve el markdown agregado — mismo patrón que
  `tests/test_integration.py`.
- `ensure_project` con un directorio temporal crea `qa-project.yaml` y reporta el estado de
  las variables sin exponer valores.
- El README documenta cómo registrar el servidor en Claude Code y en VS Code/Copilot.

## Fuera de alcance / backlog
- **Tools para las integraciones en backlog** (Xray/Jira/Trello) — se agregan cuando esos
  writers existan.
- **Verificación manual real con Copilot en VS Code** — queda para que Emanuel la haga con
  su propio entorno gráfico, documentada en el README.
