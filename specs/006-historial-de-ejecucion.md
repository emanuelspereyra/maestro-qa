# 006 — Historial de ejecución

## Problema
Hasta ahora `orchestrator.run()` devuelve un `RunResult` en memoria y nada más — no hay
forma de revisar después qué corrió, cuándo, con qué resultado. Para algo que se va a usar
en producción en CDA, eso es un hueco real de auditoría, no un detalle.

## Alcance
- Wirear `scripts/qa_history.py` del bundle vendorizado (spec 003) dentro de
  `orchestrator.run()`: un run por invocación, un evento por agente ejecutado.
- Opt-in vía parámetro `history_dir` — si no se pasa, `run()` se comporta exactamente igual
  que antes (sin tocar los tests existentes).

**Fuera de esta spec:** el dashboard de lectura (`scripts/dashboard.py`, ya mapeado a
`release_readiness` en spec 003) y exportar/consultar el historial — eso es visualización,
no generación del historial en sí.

## Diseño

**Por qué `qa_history.py` y no un logger propio:** ya está armado, probado, y hace más de lo
que haríamos nosotros de cero en poco tiempo — historial append-only en SQLite +
`events.jsonl`, con redacción automática de claves sensibles (password/token/secret/etc. en
los metadata). Reimplementarlo sería la misma duplicación que ya evitamos con
`validate_cases.py` (spec 004).

**Por qué opt-in y no siempre activo:** todos los tests existentes de `orchestrator.run()`
llaman a la función con dos argumentos y no esperan que se escriba nada a disco. Si el
historial fuera obligatorio, cada test tendría que pasar un directorio temporal — opt-in
mantiene esos tests sin cambios y agrega la capacidad como algo nuevo, no como una ruptura.

**Reutilización de la resolución de scripts vendorizados:** se extrajo
`vendor_bundle.scripts_dir()` (antes vivía duplicado dentro de `casos_manuales.py`) porque
ahora dos consumidores (el agente y el orquestador) necesitan la misma ruta a
`generate-qa-from-test-cases/scripts/`.

**Eventos registrados por run:**
1. `start-run` al principio — con el texto del intake como resumen.
2. `log` por cada agente que corrió (seleccionado y presente en `AGENT_REGISTRY`) — estado
   `EXECUTED` si no hubo error, `FAILED` si sí, incluyendo `release_readiness` cuando corre.
3. `end-run` al final — `COMPLETED`.

**Tolerancia a fallos del logging:** si `qa_history.py` no está disponible o falla, el
`run()` no se rompe — el trabajo real (generar casos, automatización, etc.) importa más que
el registro de auditoría. Se documenta como techo conocido, no se oculta (ver Backlog).

## Criterios de aceptación
- `run(intake, provider)` sin `history_dir` se comporta exactamente igual que antes (todos
  los tests existentes siguen pasando sin modificarlos).
- `run(intake, provider, history_dir=tmp_path)` crea `tmp_path/qa-history.db` y
  `tmp_path/events.jsonl` con un evento por agente ejecutado.
- Si un agente falla, el evento correspondiente queda con estado `FAILED`, no se pierde ni
  se confunde con un éxito.
- Si `qa_history.py` no existe o falla, `run()` sigue devolviendo su `RunResult` normal.

## Fuera de alcance / backlog
- **Surfacear fallos de logging** — hoy se tragan en silencio. Si en uso real se pierde
  historial sin que nadie lo note, se agrega un campo `warnings` a `RunResult` en vez de
  seguir ignorándolo.
- **Dashboard y export** — ya existen en el bundle (`dashboard.py`), se conectan cuando haga
  falta revisar el historial visualmente, no antes.
- **Multi-proyecto** — `--project` queda hardcodeado a `"maestro-qa"`; si CDA corre esto
  para más de un cliente/producto a la vez, se vuelve un parámetro real.
