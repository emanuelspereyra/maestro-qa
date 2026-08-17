# 032 — Persistir el tipo de error en el historial

## Problema
El dogfooding diario sobre `qa-history.db` encontró 2 runs únicos (`15db61cf-3e63-4d1e-9346-3489f61fcb4a`
ProcessIA y `4fda1b07-a294-457b-9e45-589caec9a6f6` HVAC, 24 eventos únicos) con 15 eventos
`FAILED` — y los 15 tienen `error_code: null`. El historial (spec 006) registra que un
agente falló, pero no de qué murió: un rate limit externo transitorio y el `KeyError:
'delivery_status'` real que motivó el PR #1 quedan indistinguibles en la misma columna
`FAILED`. Sin esa distinción, nadie puede filtrar el historial para separar ruido externo
de bugs reales del propio sistema.

**Causa raíz:** `_run_agent()` en `orchestrator.py` captura la excepción y arma
`AgentResult(error=True)` con `content=str(exc)` — el tipo de la excepción (`RuntimeError`,
`KeyError`, etc.) se descarta ahí mismo, antes de llegar a ningún lado. `_log_history()`
sólo reenvía `result.content` como `--summary`; nunca llama al `--error-code` que
`qa_history.py` (vendorizado, spec 003) ya soporta desde su CLI.

## Alcance
- `AgentResult` gana un campo opcional para el tipo de error, sin romper ningún
  constructor existente (todos usan kwargs; ver `agents/*.py` y `test_orchestrator*.py`).
- `_run_agent()` completa ese campo con `type(exc).__name__` al capturar una excepción.
- `_log_history()` pasa `--error-code` al CLI de `qa_history.py` sólo cuando el resultado
  trae ese valor.

**Fuera de esta spec:**
- Reclasificar errores existentes ya guardados en runs pasados — esta spec sólo cambia
  runs nuevos, no hace backfill del historial.
- Cualquier metadata adicional sobre el error (traceback completo, contexto del agente,
  reintentos) — sólo el nombre de la clase de excepción, que ya es información real y
  estable.
- Cambiar retries, providers, o cómo se selecciona/ordena agentes — eso es ortogonal al
  registro de historial.
- Un catálogo cerrado de códigos de error o normalización adicional (ej. mapear
  `RuntimeError` a "RATE_LIMIT") — el nombre de la clase de excepción de Python ya es
  estable y verificable; inventar una taxonomía propia es alcance no pedido por la
  evidencia.

## Diseño

**Por qué `type(exc).__name__` y no `str(exc)` o un código inventado:** `str(exc)` es el
mensaje, ya se guarda en `--summary` y varía run a run (ProcessIA vs HVAC tienen mensajes
de rate-limit distintos aunque sea el mismo tipo de falla). `type(exc).__name__` es estable
para la misma clase de problema (`KeyError` siempre es `KeyError`), no requiere inventar
metadata, y ya es lo que Python usa para distinguir familias de errores — es la señal
mínima que separa "excepción de librería/red" (`RuntimeError`, `TimeoutError`, etc.) de
"bug de nuestro propio código" (`KeyError: 'delivery_status'` del PR #1).

**Por qué en `AgentResult` y no como parámetro extra de `_log_history`:** el resultado del
agente es lo único que `_run_agent()` produce y lo único que viaja hasta `_log_history()`
en el loop de `run()` (`orchestrator.py:184-191`). Agregar el campo ahí evita pasar un
parámetro adicional por todo el camino y mantiene un solo dataclass como fuente de verdad
del resultado de un agente, éxito o error.

**Compatibilidad:** el campo nuevo (`error_code: str | None = None`) tiene default `None`.
Todos los constructores existentes de `AgentResult` en `agents/*.py` usan kwargs con menos
campos — siguen funcionando sin tocarlos. `_log_history()` sólo agrega `--error-code` al
comando cuando `result.error_code` no es `None`; en éxito (o en un `AgentResult` de test
sin el campo) el comando queda exactamente igual que hoy.

## Criterios de aceptación
- `AgentResult(agent=..., content=...)` sin `error_code` sigue funcionando en todos los
  call sites existentes (`agents/*.py`, tests) sin modificarlos.
- Un agente que lanza una excepción produce un `AgentResult` con `error=True` y
  `error_code` igual al nombre de la clase de la excepción (ej. `"KeyError"`,
  `"RuntimeError"`).
- El evento de historial correspondiente a ese fallo queda con `error_code` igual a ese
  valor en `qa-history.db` (columna `error_code`, ya existente en el esquema vendorizado).
- Un resultado exitoso (o un `AgentResult` sin `error_code`) no agrega `--error-code` al
  comando — el evento de historial queda con `error_code` en `NULL`, igual que antes.
- Suite completa (`ruff`, `mypy`, `pytest`) en verde.

## Fuera de alcance / backlog
- Backfill de runs históricos ya guardados sin `error_code` — quedan como están.
- Taxonomía propia de códigos de error más allá del nombre de la clase de excepción — se
  agrega si en el uso real `type(exc).__name__` resulta insuficiente para distinguir casos
  (ej. dos bugs distintos lanzando el mismo tipo de excepción).
- Exponer `error_code` en `RunResult.to_markdown()` — hoy nadie lo pidió; el consumo es
  vía historial, no vía el reporte en memoria.
