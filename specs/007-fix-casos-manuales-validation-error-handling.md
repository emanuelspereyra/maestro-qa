# 007 — Fix: casos_manuales validation error handling for early-error format

## Problema
El agente `casos_manuales` falla con `KeyError: 'delivery_status'` cuando `validate_cases.py` devuelve el formato de error temprano (archivo no encontrado, error de decodificación JSON, ValueError durante la carga).

`validate_cases.py` tiene dos formatos de salida:

1. **Formato error temprano** (exit code 2): `{"valid": false, "error": "..."}` — ocurre cuando:
   - El archivo de entrada no existe (OSError)
   - Error de decodificación JSON (json.JSONDecodeError)
   - Error de validación de estructura básica (ValueError en `load_document`)

2. **Formato validación normal** (exit code 0/1): reporte completo con `delivery_status`, `case_count`, `layer_counts`, `errors`, `warnings`, etc.

El código actual en `casos_manuales.py` (líneas 93-107) asume siempre el formato completo:
```python
report = json.loads(validation.stdout)
if report.get("errors"):  # error temprano usa "error" (singular), no "errors"
    raise ValueError(...)

summary = f"Cobertura: {report['delivery_status']} ..."  # KeyError aquí!
```

## Alcance
- Manejar ambos formatos de respuesta de `validate_cases.py` en `casos_manuales.py`
- Agregar test para el formato de error temprano
- No cambiar `validate_cases.py` — es código vendorizado

## Diseño

### Detección del formato
El formato de error temprano se detecta por la presencia de la clave `"error"` (singular) y ausencia de `"delivery_status"`.

### Manejo del error temprano
Cuando se detecta el formato de error temprano:
1. Levantar `ValueError` con el mensaje de error incluido (igual que se hace con `errors` en el formato normal)
2. No intentar acceder a claves que no existen

### Código propuesto
```python
report = json.loads(validation.stdout)

# Formato error temprano: {"valid": false, "error": "..."}
if "error" in report and "delivery_status" not in report:
    raise ValueError(f"Validación falló (error temprano): {report['error']}")

# Formato normal: tiene delivery_status, errors, warnings, etc.
if report.get("errors"):
    raise ValueError(f"Casos inválidos: {'; '.join(report['errors'])}")

summary = (
    f"Cobertura: {report['delivery_status']} — {report['case_count']} casos, "
    f"capas {report['layer_counts']}"
)
```

## Criterios de aceptación
- Con `validate_cases.py` devolviendo formato error temprano (ej. archivo no encontrado), el agente levanta `ValueError` con el mensaje de error, no `KeyError`
- Con `validate_cases.py` devolviendo formato normal con `errors`, el agente levanta `ValueError` con los errores (comportamiento existente)
- Con `validate_cases.py` devolviendo formato normal sin `errors`, el agente genera el resumen correctamente (comportamiento existente)
- Test nuevo cubre el formato error temprano
- Tests existentes siguen pasando

## Fuera de alcance
- Cambios a `validate_cases.py` (es vendorizado)
- Reintentos automáticos — el orquestador ya maneja excepciones de agentes