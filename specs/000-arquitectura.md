# 000 — Arquitectura general

## Problema
CDA necesita testing (casos manuales, automatización, regresión, performance, seguridad,
etc.) más rápido sin depender de que cada QA arranque de cero por tarea. El equipo ya usa
distintos asistentes de IA (Claude Code, GitHub Copilot, y potencialmente otros) — la
solución no puede estar atada a uno solo.

## Alcance
Un orquestador ("Maestro QA") que recibe una tarea de testing (ticket de Jira o spec/PRD),
decide qué agentes especializados activar, y junta sus resultados en un output único.

Queda **fuera** de esta spec: la implementación de cada agente especializado (tiene su
propia spec) y la API REST para plataformas sin soporte MCP (ver sección Backlog).

## Diseño

**Capas:**

1. **Motor core** (`src/maestro_qa/`) — lógica de negocio, agnóstica de qué LLM la ejecuta.
   Vive en `providers/` (adaptador común para Anthropic y proveedores compatibles con el
   formato de OpenAI: OpenAI, Gemini, Kimi/Moonshot, Qwen, DeepSeek) y `agents/` (un módulo
   por agente especializado).
2. **Orquestador** (`orchestrator.py`) — recibe el input, clasifica qué agentes corresponden,
   los invoca, agrega resultados.
3. **Exposición MCP** (`mcp_server.py`) — envuelve al orquestador como servidor MCP. Esto es
   lo que lo hace usable desde Claude Code y GitHub Copilot sin código adicional en el
   cliente, porque ambos hablan MCP nativamente.

**Por qué MCP y no una integración por plataforma:** Claude Code, Copilot, Gemini, ChatGPT,
Kimi, Qwen y DeepSeek tienen mecanismos de extensión incompatibles entre sí. Construir 7
integraciones nativas significa reimplementar la misma lógica 7 veces. Un solo servidor MCP
cubre Claude Code + Copilot de fábrica; el resto queda en backlog explícito hasta que haga
falta (ver abajo).

**Selección de proveedor de LLM:** configurable por cliente (CDA elige qué LLM usa cada
agente, no queda atado a un solo proveedor).

## Criterios de aceptación
- El repo instala (`pip install -e .`) y el paquete `maestro_qa` importa sin errores.
- CI corre lint (ruff) + type-check (mypy) + tests en cada PR.
- Cada feature nueva (agente, integración) tiene su propia spec en `specs/` antes de tener
  código, siguiendo `specs/TEMPLATE.md`.

## Fuera de alcance / backlog
- **API REST standalone** para plataformas sin MCP maduro (ChatGPT, Kimi, Qwen, DeepSeek).
  Decisión explícita: no se construye en v1. Cuando se construya, expone el mismo
  `orchestrator.py` — no se reimplementa la lógica.
- **Wrapper Custom GPT Action** para ChatGPT — depende de que exista la API REST.
