# Automatización funcional

## Contenido

- Reglas generales
- Frontend con Playwright Python
- APIs en Python y REST Assured
- APIs de terceros y mocks contractuales
- Datos y cleanup
- Flaky tests
- Análisis de cambios

## Reglas generales

Generar código mantenible y ejecutable, no pseudocódigo presentado como terminado. Si faltan URL, autenticación, selector, contrato o dato, marcar el punto como pendiente y no inventarlo.

Vincular cada test con `case_id`, `dataset_id`, versión y evidencia.

No fijar `dev`, `main`, URLs o credenciales en el código de prueba. Seleccionar el ambiente mediante `QA_TARGET_ENV` y resolver valores con el prefijo `QA_<AMBIENTE>_`. Reutilizar `assets/playwright-python/qa_environment.py` y el patrón de `conftest.py` en suites frontend y API.

Automatizar por capa:

- Casos `frontend`: Playwright con pytest.
- Casos `backend`: pytest + HTTPX o REST Assured cuando se haya aprobado Java.
- Casos `e2e`: Playwright coordinado con setup/verificación por API o base autorizada.

No entregar únicamente automatización backend cuando la matriz de cobertura requiere frontend. Si una capa queda bloqueada, conservar sus casos manuales y registrar el motivo que impide automatizar o ejecutar.

Separar:

- Setup de ambiente.
- Setup de datos.
- Acción.
- Oracle.
- Evidencia.
- Cleanup.

## Frontend con Playwright Python

Usar pytest y `pytest-playwright`. Reutilizar `assets/playwright-python/` como base cuando el proyecto no tenga estructura. Copiar `.env.example` como inventario de variables, pero no confirmar ni versionar un `.env` con secretos.

Las fixtures `qa_target_environment`, `base_url` y `api_base_url` deben resolver el perfil al iniciar pytest. `qa_environment.py` carga `.env` o el archivo indicado por `QA_ENV_FILE` sin ejecutar shell y sin sobrescribir variables del proceso. Incluir el ambiente efectivo en el encabezado del reporte y en `qa_run_id`.

Preferir:

- Locators por rol, label, placeholder o test ID.
- Web-first assertions.
- Contexto aislado por test.
- Storage state seguro para sesiones.
- Fixtures pequeñas y composables.
- Page Objects solo cuando reduzcan duplicación real.
- Traces, screenshots y videos configurables.

Evitar:

- `time.sleep`.
- XPath o CSS frágil sin justificación.
- Dependencias entre tests.
- Reutilizar datos mutables sin aislamiento.
- Capturar tokens en logs.
- Self-healing silencioso.

Estructura sugerida:

```text
tests/
├── conftest.py
├── pages/
├── fixtures/
├── data/
└── test_<feature>.py
```

## APIs en Python

Para un stack completamente Python, usar:

- pytest.
- HTTPX o requests según el proyecto.
- Pydantic o JSON Schema para contratos.
- Fixtures para cliente autenticado y datos.

El cliente API debe recibir `API_BASE_URL`, usuario, contraseña o token mediante el mismo resolvedor multiambiente. No mantener un segundo selector de ambiente independiente para backend.

Antes de iniciar pytest, comparar `FRONTEND_URL` y `API_BASE_URL` con `qa-knowledge/environment-routes.json`. Las rutas de autenticación, administración u OpenAPI separadas usan `AUTH_URL`, `ADMIN_URL` y `OPENAPI_URL` bajo el mismo prefijo de ambiente.

Tratar valores vacíos, `CHANGE_ME`, `TODO`, `<...>` y `${...}` como configuración faltante. No permitir que un placeholder llegue a un login o request.

Validar:

- Status.
- Schema.
- Campos relevantes.
- Headers importantes.
- Errores.
- Autorización.
- Idempotencia cuando aplique.
- Persistencia o efecto observable.

No registrar Authorization, cookies ni cuerpos sensibles.

## APIs de terceros y mocks contractuales

Leer [external-service-mocking.md](external-service-mocking.md) cuando el setup o el flujo dependa de un proveedor externo. Inyectar su URL mediante el perfil `QA_<AMBIENTE>_`; no hardcodear el host local ni agregar switches de mock al código productivo.

Etiquetar cada ejecución con servicio, modo, escenario y versión del contrato. Separar las suites `contract-mock` y `real-sandbox`: la primera valida la lógica controlable del sistema y la segunda valida la integración efectiva. No sumar un caso mockeado como integración real aprobada.

## REST Assured

REST Assured es una DSL Java. Generarlo únicamente si el cliente acepta un módulo Java y runtime JVM. No etiquetarlo como Python.

Si el cliente pide “estilo Rest Assured en Python”, usar pytest + HTTPX con helpers `given/when/then`, sin afirmar que se usa REST Assured.

## Datos

Antes del test:

1. Ejecutar preflight.
2. Crear dataset por API, DB, UI o fixture.
3. Registrar IDs creados.

Después:

1. Capturar resultado.
2. Generar consultas de verificación filtradas con `scripts/generate_verification_queries.py`.
3. Limpiar en orden inverso.
4. Registrar residuos o cleanup fallido y conservar las consultas como evidencia del run.

## Flaky tests

Medir frecuencia y patrón. Clasificar causa:

- Sincronización.
- Datos compartidos.
- Dependencia externa.
- Selector inestable.
- Ambiente.
- Defecto intermitente.
- No determinado.

Permitir reintentos limitados solo para diagnóstico y registrar cada intento. No usar el éxito de un retry para ocultar el fallo inicial.

## Análisis de cambios

Comparar rutas, endpoints, schemas, selectores estables, modelos y commits. Proponer suites afectadas con explicación.

No editar automáticamente oracles confirmados cuando cambia la aplicación.
