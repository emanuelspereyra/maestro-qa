# 031 — `casos_manuales`: reconocer la forma de error singular del validador

## Problema
Detectado por auto-dogfooding diario (qa-history, run ProcessIA
`15db61cf-3e63-4d1e-9346-3489f61fcb4a`): `casos_manuales` falló con `KeyError:
'delivery_status'`, y como el agente no distinguió esto de un fallo real, `trazabilidad`
quedó sin contexto y reportó 0 cubiertos / 7 huecos en cascada.

Causa raíz: cuando el LLM devuelve una capa (`layer`) fuera de las 5 válidas del vendor
(`frontend|backend|e2e|data|performance` — ej. `Frontend` con mayúscula o `mobile`),
`validate_cases.py` corta temprano en `normalize_required_layers` y devuelve
`{"valid": false, "error": "Invalid required layers: ..."}` (campo `error` singular, sin
`errors` ni `delivery_status`). `casos_manuales.py` solo miraba `report.get("errors")`
(plural) — con ese chequeo en falso, seguía de largo hasta indexar
`report['delivery_status']`, y ahí volaba el `KeyError` en vez de un error legible.

## Alcance
- El consumidor (`src/maestro_qa/agents/casos_manuales.py`) reconoce explícitamente la
  forma `{"valid": false, "error": "..."}` que devuelve `validate_cases.py` cuando falla
  antes de calcular cobertura (capas o familias de escenario inválidas a nivel de
  argumento), y levanta `ValueError` con ese mensaje — mismo tratamiento que ya recibe la
  forma `{"errors": [...]}` de fallos de esquema por caso.
- No se filtran ni se normalizan silenciosamente capas inválidas del lado de
  `casos_manuales.py`: si el LLM generó una capa que no existe, es una señal real de que
  el LLM no siguió el contrato, y debilitar la validación escondería el problema en vez de
  reportarlo.

**Fuera de esta spec:**
- No se toca `src/maestro_qa/vendor/` — el vendor bundle ya devuelve una forma de error
  consistente para este caso, el bug es solo del lado del consumidor.
- Reintento automático del LLM ante capa inválida — sigue siendo backlog desde spec 004,
  el orquestador ya captura la excepción sin abortar a los demás agentes.

## Diseño
`validate_cases.py` tiene dos formas de fallo distintas:
1. Fallo temprano de argumentos/config (capas o familias de escenario inválidas en
   `coverage`) → `{"valid": false, "error": "<mensaje>"}`, exit code 2, sin `delivery_status`
   ni `errors`.
2. Fallo de esquema por caso (campos faltantes, tipos incorrectos) → reporte completo con
   `delivery_status` y una lista `errors` (puede venir vacía).

`casos_manuales.py` ya manejaba (2). Se agrega el chequeo de (1) en el mismo punto, antes
del chequeo de `errors` y antes de correr `render_manual_cases.py` (no tiene sentido
renderizar si la validación ni siquiera corrió):

```python
report = json.loads(validation.stdout)
if report.get("error"):
    raise ValueError(f"Casos inválidos: {report['error']}")
if report.get("errors"):
    raise ValueError(f"Casos inválidos: {'; '.join(report['errors'])}")
```

Mismo formato de mensaje (`"Casos inválidos: ..."`) que el camino existente, para que el
orquestador y los reportes lo traten igual.

## Criterios de aceptación
- Un caso con `layer` fuera de `frontend|backend|e2e|data|performance` (ej. `"mobile"`)
  hace que el agente levante `ValueError` con el texto de `validate_cases.py`
  (`"Invalid required layers: ..."`), no `KeyError: 'delivery_status'`.
- El camino existente de errores de esquema por caso (`{"errors": [...]}`) sigue
  funcionando igual que antes.
- El camino feliz (casos válidos) no cambia.

## Fuera de alcance / backlog
- Reintento automático del LLM ante capa inválida — backlog desde spec 004.
- Normalizar/mapear capas casi-válidas (ej. `"Frontend"` → `"frontend"`) — no está pedido
  y escondería el error real del LLM en vez de reportarlo.
