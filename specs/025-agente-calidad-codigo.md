# 025 — Agente: calidad de código (anti AI-slop)

## Problema
Ningún agente del fleet revisa calidad de código — los 10 existentes generan artefactos
(casos, automatización, datos, etc.) a partir del texto del ticket, pero nadie audita el
código resultante en busca de sobre-ingeniería, abstracciones innecesarias, código muerto
o "AI slop" en general (patrones típicos de código generado por LLM sin revisión: helpers
para un solo uso, validación de escenarios imposibles, comentarios que repiten el código,
scaffolding "para después"). Emanuel pidió explícitamente agregar un agente que aplique
estos criterios (los mismos de la skill "ponytail" que gobierna cómo yo mismo escribo
código en este repo) sobre código real, no solo sobre lo que yo genero en esta sesión.

## Alcance
Nuevo agente `calidad_codigo`, con tres fuentes de código posibles (las tres pedidas
explícitamente, no una a elección):
1. **Código pegado en el ticket** — un diff o snippet incluido en el texto del intake.
2. **El repo real de frontend** — mismo mecanismo de `repo_access.py`/spec 023, pero
   **solo lectura** (`list_files`/`read_file`, nunca `write_file` — un agente de revisión
   nunca debe poder escribir).
3. **Código generado por `automatizacion`/`automatizacion_api` en el mismo run** — si
   alguno de los dos corrió antes en el mismo ticket, su resultado se inyecta como
   contexto (mismo patrón de spec 008 con `casos_manuales`, pero dirigido solo a este
   agente).

Se activa de dos formas (ambas pedidas):
- **Por keyword** en el ticket, igual que el resto del fleet — no cambia el
  comportamiento por defecto de nadie más.
- **Por comando de consola**, standalone, sin pasar por el orquestador/clasificación —
  para revisar un archivo o diff puntual sin necesitar armar un ticket.

**Fuera de esta spec:**
- Push/PR o cualquier escritura — este agente es de solo lectura, punto. Si algún día se
  quiere que proponga un patch aplicable, es una spec nueva.
- Ejecutar linters/type-checkers reales (ruff, mypy, eslint) sobre el código del cliente —
  esto es una revisión cualitativa por LLM, no una corrida de herramientas. Si se quiere
  eso, es un agente distinto o una extensión de `seguridad` (que ya integra SonarQube).
- Revisar el código de Maestro QA mismo — este agente revisa el código de un ticket/
  cliente, no hace introspección del propio repo (eso fue lo que hizo la sesión de
  auditoría manual, no algo que se automatice acá).

## Diseño

### Prompt
El system prompt traduce los principios de la skill "ponytail" a una revisión de código
ajeno (no a cómo escribir código propio): la escalera de "¿hace falta que esto exista?
¿ya está en el codebase? ¿lo resuelve la stdlib/una dependencia ya instalada?", sin
abstracciones no pedidas, sin boilerplate para escenarios imposibles, comentarios que
solo valen si explican un PORQUÉ no obvio, deletion over addition. Es agnóstico de
lenguaje — el código a revisar puede ser Python, JS/TS, lo que sea.

### Salida
```json
{
  "findings": [
    {
      "location": "archivo:línea o descripción del bloque si no hay línea exacta",
      "severity": "alta|media|baja",
      "problem": "qué patrón de sobre-ingeniería/código muerto/abstracción innecesaria se encontró",
      "suggestion": "qué simplificar o eliminar, concreto"
    }
  ],
  "pending_items": ["si no hubo código real para revisar (ninguna de las 3 fuentes tenía contenido), decirlo acá en vez de inventar hallazgos"]
}
```
`findings` puede ser una lista vacía — significa "código ya lazy, sin hallazgos", no un
error. Si CERO fuentes de código están disponibles (nada en el ticket, sin repo
configurado, automatizacion no corrió), el agente igual corre pero declara en
`pending_items` que no tuvo nada que revisar, en vez de alucinar hallazgos.

### Acceso a repo (solo lectura)
Reusa `repo_access.get_frontend_repo()` tal cual (spec 023) para el clone/verificación,
pero le ofrece al LLM únicamente `repo_access.READ_ONLY_TOOLS` (`list_files`/`read_file`)
— `write_file` ni se declara en el schema. Como defensa en profundidad (mismo criterio
que el bug de `.git/` de la auditoría anterior), el `tool_executor` que se le pasa al
provider rechaza explícitamente cualquier llamada a `write_file` aunque el LLM la
alucine sin que se la hayan ofrecido.

### Orquestador: orden y contexto
`calidad_codigo` corre DESPUÉS de todos los agentes "normales" (peso 1) y después de
`casos_manuales`, pero antes de `release_readiness` — necesita ver el resultado de
`automatizacion`/`automatizacion_api` de la misma corrida. El orquestador trackea esos
dos resultados durante el loop (mismo patrón que ya trackea `casos_result`) y arma una
nueva función `_with_code_context()` que le agrega a la intake de `calidad_codigo` (y
solo a la de `calidad_codigo`, no a todos como `_with_casos_context`) una sección
"Código generado en este run:" con el contenido de ambos si están disponibles y sin
error.

### Comando de consola
`scripts/revisar_codigo.py <path>` — toma un path a un archivo (código o diff), arma un
`Intake(source="spec", ...)` con ese contenido pegado, y llama a
`CalidadCodigoAgent().run(intake, provider)` directo, sin pasar por
`orchestrator.classify_agents`/`run()`. Mismo patrón que `scripts/smoke_test.py` — no
corre en CI (necesita API key real), es para uso manual.

## Criterios de aceptación
- Con un `FakeProvider`, el agente parsea `findings`/`pending_items`, valida severidad, y
  renderiza markdown legible por hallazgo.
- Sin ninguna de las 3 fuentes de código disponibles, el agente igual corre y reporta en
  `pending_items` que no tuvo código real para revisar.
- Con un repo real local (mismo patrón de test que spec 023), el LLM puede `list_files`/
  `read_file` pero un intento de `write_file` (aunque no esté en el schema ofrecido) es
  rechazado por el `tool_executor`.
- Un ticket con "revisar código"/"code review"/"refactor"/"calidad de código" rutea a
  `calidad_codigo`; un ticket sin esas palabras no lo activa.
- Si `automatizacion` corrió en el mismo run y generó código, `calidad_codigo` lo recibe
  como contexto — verificado con un test de integración del orquestador.
- `scripts/revisar_codigo.py` existe y sigue el mismo patrón que
  `scripts/smoke_test.py`.
- Suite completa (`ruff`, `mypy`, `pytest`) en verde.

## Fuera de alcance / backlog
- Aplicar el mismo patrón de contexto-inyectado a otros pares de agentes (hoy es
  específico a automatizacion/automatizacion_api → calidad_codigo).
- Exponer esto también como tool de MCP (`revisar_codigo(...)`) — no pedido, solo consola
  y ticket por ahora. Se agrega si se necesita.
- Reusar el mismo repo cacheado que `automatizacion` en la misma corrida (hoy cada
  agente llama a `get_frontend_repo()` por separado, re-clona/refresca) — optimización,
  no correctness, mismo ítem de backlog que ya existía en spec 023.
