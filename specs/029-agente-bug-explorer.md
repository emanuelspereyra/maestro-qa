# 029 — Agente: bug_explorer (trazar un bug a archivo:línea)

## Problema
Ningún agente del fleet toma la descripción de un bug y la traza a una causa probable en
el código real. `priorizacion_bugs` redacta un borrador de defecto (severidad, pasos,
resultado esperado/real) pero nunca mira código — `calidad_codigo` mira código real pero
para calidad, no para encontrar la causa de un bug reportado. Pedido explícito de
Emanuel: "bug-explorer — describe a bug, get the likely cause traced to a specific file
and line".

## Alcance
Nuevo agente `bug_explorer`, mismo esqueleto de acceso a repo de solo lectura que
`calidad_codigo` (spec 025) — reusa `repo_access.get_frontend_repo`/`READ_ONLY_TOOLS`/
`read_only_executor()` tal cual, sin escribir nada nunca. Toma la descripción del bug
del ticket (síntoma, pasos, esperado/real) y devuelve una lista de causas probables con
archivo/línea cuando el repo real está disponible, o una hipótesis conceptual (sin
inventar un path que no vio) cuando no lo está.

Se activa igual que `calidad_codigo`: por keyword en el ticket, y también standalone vía
un script de consola (mismo patrón que `scripts/revisar_codigo.py`).

**Fuera de esta spec:**
- Backend (`repositories.backend`) — igual que `calidad_codigo`, queda scoped a frontend
  por ahora; la generalización de `repo_access.get_repo()` (spec 026) ya permite
  extenderlo cuando se pida, sin rediseñar nada.
- Aplicar el fix — este agente traza la causa probable, no escribe código (ninguna tool
  de escritura, igual que `calidad_codigo`).
- Ejecutar el código para reproducir el bug — sin sandbox de ejecución en este proyecto,
  el agente razona sobre el código estático, no lo corre.

## Diseño

### Prompt
Instruye al LLM a: leer la descripción del bug (síntoma, pasos, esperado vs real), y si
tiene acceso a `list_files`/`read_file`, explorar el repo buscando el código relacionado
antes de proponer una causa. Regla explícita: si no tiene acceso al repo real, o no
encontró nada concreto, NUNCA inventa un path/línea — propone la hipótesis en términos
conceptuales (`file`/`line` en `null`) o la deja en `pending_items`.

### Salida
```json
{
  "likely_causes": [
    {
      "file": "src/pages/login.py o null si es conceptual",
      "line": 42,
      "confidence": "alta|media|baja",
      "reasoning": "por qué se sospecha este lugar",
      "suggested_direction": "qué revisar/cambiar — no un fix aplicado"
    }
  ],
  "pending_items": ["si no se pudo identificar nada concreto, o falta info del bug"]
}
```
`file`/`line`/`suggested_direction` opcionales (pueden ser `null`) — `confidence` y
`reasoning` son los únicos obligatorios por causa.

### Repo access y consola
Idéntico a `calidad_codigo`: `READ_ONLY_TOOLS`, `read_only_executor()`, fallback a
razonar solo con la descripción si no hay repo o si el tool-calling falla a mitad de
camino. `scripts/explorar_bug.py <archivo-con-la-descripcion-del-bug>` — mismo patrón
que `scripts/revisar_codigo.py`.

## Criterios de aceptación
- Con un `FakeProvider`, parsea `likely_causes`/`pending_items`, valida `confidence`,
  renderiza markdown legible.
- Sin repo configurado: sigue funcionando, reporta causas conceptuales o pending_items,
  nunca inventa un file/line falso (no hay forma de testear "no inventa" directamente,
  pero el prompt lo prohíbe explícitamente y ningún test espera un path fabricado).
- Con un repo real local (mismo patrón de test que spec 025): el LLM puede
  `list_files`/`read_file`, un intento de `write_file` es rechazado igual.
- Falla de repo access o de tool-calling cae a razonar solo con la descripción, nunca
  rompe la corrida completa.
- Un ticket con palabras de bug ("bug", "error", "no funciona", "traza el bug") rutea a
  `bug_explorer` — mismo criterio de cuidado con falsos positivos que la keyword "carga"
  arreglada en la auditoría anterior.
- `scripts/explorar_bug.py` existe, mismo patrón que `scripts/revisar_codigo.py`.
- Suite completa (`ruff`, `mypy`, `pytest`) en verde.

## Fuera de alcance / backlog
- `repositories.backend` — mismo patrón, se extiende cuando se pida.
- Tool de MCP dedicada — solo ticket + consola por ahora, como `calidad_codigo`.
