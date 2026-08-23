# 033 — Persistir duración de agentes en el historial

## Problema
El esquema del historial de ejecución (spec 006) contempla `duration_ms`, pero el
orquestador nunca manda ese dato. Las 2 corridas auditadas suman 23 eventos: 19 eventos
de agente (13 ProcessIA + 6 HVAC) y 4 eventos `start-run`/`end-run`. Los 19/19 eventos de
agente tienen `duration_ms` NULL. Sin esas duraciones no se puede distinguir un agente
lento de uno rápido ni detectar regresiones de performance en los propios agentes — la
auditoría histórica queda incompleta.

## Alcance
- `orchestrator.py`: `AgentResult` gana `duration_ms: int | None`; se mide con reloj
  monotónico de alta resolución (`time.perf_counter`) alrededor de `agent.run()`, tanto
  en éxito como en excepción, y `_log_history()` agrega `--duration-ms` al evento solo
  cuando hay valor.
- El vendor ya soporta el flag y la columna (`qa_history.py`: `--duration-ms`,
  `events.duration_ms INTEGER`) — cero cambios ahí.

## Diseño
- Medición en `_run_agent()` (único punto por donde pasa todo agente, incluido
  `release_readiness`): se toma `perf_counter()` antes de `agent.run()` y después,
  en éxito o excepción. Milisegundos enteros, no negativos (`max(0, ...)`). Los eventos
  `start-run`/`end-run` no representan una llamada de agente y quedan sin duración.
- `duration_ms` es opcional con default `None` para mantener compatibilidad: cualquier
  `AgentResult` construido a mano (tests, usos futuros) sigue siendo válido, y
  `_log_history()` simplemente omite el flag cuando es `None`.
- El historial sigue siendo auditoría best-effort (spec 006): si el log falla, `run()`
  no se entera.

## Criterios de aceptación
- Éxito: evento `EXECUTED` persiste la duración esperada (probado con reloj fake,
  sin sleeps).
- Excepción: evento `FAILED` también persiste su duración.
- `AgentResult(duration_ms=None)` loguea sin `--duration-ms`, igual que antes.
- Tests focales de historial en verde; sin cambios de comportamiento visible fuera del
  historial.

## Fuera de alcance / backfill
- Backfill de los 19 eventos históricos de agente con duración NULL — no tiene sentido
  inventar duraciones pasadas; se miden desde ahora.
- Alertas o umbrales sobre duración (ej. "avisar si un agente tarda > X") — primero
  hace falta data real acumulada.
- Cambios al vendor o al esquema SQLite — ya soportan todo lo necesario.
