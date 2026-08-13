# Mocking de APIs de terceros

## Cuándo usarlo

Usar un mock cuando la preparación de datos o el flujo bajo prueba depende de un proveedor externo y se necesita una respuesta determinista, el sandbox no está disponible o deben probarse errores difíciles de provocar. No usarlo para afirmar que la integración real funciona.

Clasificar cada dependencia:

- `real-sandbox`: proveedor real no productivo; valida integración y contrato efectivos.
- `contract-mock`: respuesta local derivada de un contrato versionado.
- `sanitized-fixture`: payload estático sanitizado cuando no puede ejecutarse un servidor.
- `blocked`: no existe contrato confiable, sandbox ni autorización para simular.

Mantener al menos una suite separada contra `real-sandbox` cuando la integración con el proveedor sea parte del objetivo. Un test con mock puede verificar la lógica propia, los reintentos y la persistencia, pero no DNS, TLS, credenciales, disponibilidad ni comportamiento real del tercero.

## Descubrimiento y decisión

Por cada servicio externo:

1. Identificar qué datos crea, consulta o modifica y qué caso los necesita.
2. Buscar contrato en OpenAPI, Postman, documentación, SDK, código cliente o tráfico observado sanitizado.
3. Preguntar si hay sandbox y si el mocking está autorizado. No redirigir tráfico real sin consentimiento.
4. Registrar propietario, versión del contrato, URL por ambiente, autenticación requerida, efectos y PII.
5. Elegir el modo por suite y documentar la limitación del oracle.

Si no existe evidencia suficiente del contrato, crear un borrador marcado `inferred` y bloquear su uso como prueba contractual hasta validarlo.

## Catálogo de escenarios

Partir de `assets/third-party-mock.template.json`. Cubrir cuando apliquen:

- Éxito y respuesta alternativa válida.
- Error de validación, autenticación, autorización, inexistencia y conflicto.
- Rate limit `429` y encabezado de reintento.
- Respuesta lenta, timeout y conexión no disponible.
- `5xx`, cuerpo parcial, esquema inválido o JSON malformado.
- Respuesta duplicada, evento repetido, orden alterado e idempotencia.
- Reintento exitoso y agotamiento de reintentos.

Seleccionar el escenario con `X-QA-Mock-Scenario` o `qa_scenario` cuando la suite llame directamente al mock. Si la llamada nace dentro de la aplicación y no puede enviar controles QA, iniciar el servidor con `--scenario <nombre>`. No introducir la selección del mock en código productivo; inyectar la URL desde la configuración del ambiente.

## Servidor local

Validar el catálogo:

```bash
python scripts/mock_api_server.py mock-catalog.json --check
```

Iniciarlo en loopback:

```bash
python scripts/mock_api_server.py mock-catalog.json --host 127.0.0.1 --port 8765
```

Para forzar un error del proveedor durante todo ese proceso:

```bash
python scripts/mock_api_server.py mock-catalog.json --scenario provider-error
```

Configurar la aplicación o suite con una variable por ambiente, por ejemplo `QA_QA_PAYMENTS_BASE_URL=http://127.0.0.1:8765`. El servidor no registra headers ni cuerpos y rechaza binds no locales salvo `--allow-nonlocal`; usar esa excepción solo dentro de una red QA aislada.

## Trazabilidad y evidencia

Agregar a cada caso o resultado:

- `external_dependency_mode`
- `external_service`
- `mock_scenario`
- `contract_version`
- `mock_catalog_path`
- `real_integration_covered_by`

Registrar `mock-catalog-validated`, `mock-started`, `mock-scenario-used` y `mock-stopped`. Marcar claramente el reporte con `MOCKED_DEPENDENCY`; no mezclar sus métricas con la suite real de integración.

## Seguridad

- No copiar secretos, PII real, tokens ni cuerpos productivos sin sanitizar.
- No permitir que el mock acepte tráfico externo por defecto.
- No simular éxito para ocultar un proveedor caído en una suite que requiere integración real.
- No grabar requests automáticamente. Si se autoriza captura, conservar solo campos permitidos y sanitizados.
- No usar un mock de pago, email, firma o identidad para ejecutar efectos reales.
