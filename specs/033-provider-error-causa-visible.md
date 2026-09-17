# 033 — Que el "exhausted retries" muestre la causa real

## Problema
El dogfooding diario sobre los dos `qa-history` disponibles (ProcessIA `15db61cf-…` y
HVAC `4fda1b07-…`, 23 eventos en total) encontró **14 eventos `FAILED` con el mismo texto
críptico `exhausted 3 retries`**, repartidos en 11 módulos distintos (automatizacion_api,
priorizacion_bugs, documentacion, regresion, performance, seguridad, bug_explorer,
calidad_codigo, release_readiness, trazabilidad). El motivo exacto de cada uno es un
callejón sin salida: tras agotarse los reintentos, `with_retries()` lanza
`ProviderError("exhausted 3 retries")` y la excepción transitoria original — que es la
única señal diagnóstica (rate limit vs timeout vs fallo de conexión vs 5xx) — queda
desechada. Por eso el historial registra 14 fallos idénticos: **no se puede distinguir ruido
externo transitorio de un bug real**.

La spec 032 (PR `error-code-historial`) persiste `type(exc).__name__` como `error_code`,
lo que ayuda a separar `KeyError` de `ProviderError`; pero para todos estos 14 casos el
tipo es el mismo `ProviderError`, así que sigue sin distinguir rate limit de timeout. Las
specs 032 (reintentos/contexto del error) y 006 (historial) dejan explícitamente este
detalle como backlog.

**Causa raíz:** `retry.py:27` levanta `raise ProviderError(f"exhausted {max_attempts} retries") from exc`. El `__cause__` queda en el objeto de la excepción (visible programáticamente), pero el *mensaje* (`str(exc)`) — que es justamente lo que `orchestrator.py:_run_agent()` mete en `AgentResult.content` y `_log_history()` vuelca en el `summary` del histórico — no contiene nada de la causa. Todo lo que cruza al historial es el mensaje, no el objeto.

## Alcance
- `ProviderError` incluye en su **mensaje** el tipo y mensaje de la excepción transitoria
  subyacente, de modo que `str(ProviderError(...))` sea diagnóstica, p. ej.
  `exhausted 3 retries (RateLimitError: 429 you are sending too many requests)` en vez de
  `exhausted 3 retries`.
- El error se sigue lanzando como `ProviderError` y conserva `__cause__` (sin cambios de
  contrato). Solo cambia el texto del mensaje.
- Se actualiza el test existente `test_raises_provider_error_after_exhausting_retries`
  y se agrega cobertura para el nuevo mensaje con causa.

**Fuera de esta spec:**
- Cualquier cambio al esquema de historial (eso es la 032).
- Retries más inteligentes, backoff distinto, o cambiar `is_transient` de los providers.
- Exponer el `__cause__` como campo estructurado en el historial — solo el mensaje, que es
  lo que ya viaja por `summary`.
- Backfill de runs históricos ya guardados.

## Diseño
En `src/maestro_qa/providers/retry.py`, `with_retries()` guarda la última excepción
transitoria dentro del `except` y, al agotar reintentos, la pasa al `ProviderError`:

```python
try:
    return fn()
except Exception as exc:
    if not is_transient(exc):
        raise
    last_exc = exc
    attempt += 1
    if attempt >= max_attempts:
        detail = f" ({type(last_exc).__name__}: {last_exc})" if last_exc is not None else ""
        raise ProviderError(f"exhausted {max_attempts} retries{detail}") from last_exc
    time.sleep(backoff_base * (2 ** (attempt - 1)))
```

El mensaje del error subyacente (`last_exc`) ya apareció en el historial de forma
críptica (por ej. `'delivery_status'` es el `str` de un `KeyError`), así que reusar el mismo
formato `type: message` es coherente con lo que la tool ya vuelca en `summary`. Si la
excepción transitoria no tiene `str` útil queda el nombre de la clase igualmente.

**Compatibilidad:** `ProviderError` sigue siendo `ProviderError`, `__cause__` sigue
seteado, y el único cambio observable es el texto. Ningún call site de `with_retries`/
`ProviderError` cambia su firma.

## Criterios de aceptación
- Una excepción transitoria que agota reintentos produce `ProviderError` cuyo `str()`
  contiene el nombre de clase y el mensaje de la excepción original (ej.
  `RateLimitError`).
- Se sigue lanzando `ProviderError` (el test existente de `pytest.raises(ProviderError)`
  sigue pasando) y `__cause__` queda seteado a la excepción transitoria final.
- Una excepción permanente sigue propagándose inmediatamente, sin wrapper.
- El flujo feliz que recupera tras errores transitorios no cambia.
- Suite completa (`ruff`, `mypy`, `pytest`) en verde.

## Fuera de alcance / backlog
- Persistir la causa como columna estructurada — la 032 ya cubre `error_code`; si `type:
message` en `summary` no alcanza para separar casos, se agrega metadata al histórico.
- Reintentos o backoff inteligentes.
- Backfill del historial viejo.
