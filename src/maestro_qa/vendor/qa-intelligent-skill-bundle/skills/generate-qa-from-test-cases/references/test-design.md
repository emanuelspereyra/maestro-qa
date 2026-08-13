# Diseño de casos y trazabilidad

## Contenido

- Contrato canónico
- Formato manual legible
- Cobertura obligatoria por capas
- Cobertura integral por familias y reglas
- Diseño manual
- Selección para automatización
- Priorización por riesgo
- Trazabilidad
- Calidad del caso

## Contrato canónico

Representar cada caso con:

```json
{
  "case_id": "FE-TC-001",
  "feature_id": "users.create",
  "layer": "frontend",
  "scenario_family": "happy-path",
  "business_rule_ids": ["BR-USERS-001"],
  "coverage_dimensions": ["authorized-role", "valid-data", "created-state"],
  "title": "Crear usuario válido",
  "objective": "Verificar la creación de un usuario",
  "sources": ["REQ-12", "api-catalog:/users"],
  "work_item_ids": ["JIRA:ABC-123"],
  "confidence": "confirmed",
  "priority": "high",
  "risk": "authorization",
  "execution_type": "both",
  "preconditions": ["Ambiente QA disponible"],
  "steps": [
    {"order": 1, "action": "Abrir formulario", "expected": "Formulario visible"}
  ],
  "expected_result": "Usuario creado y visible",
  "actual_result": "Pendiente",
  "status": "NOT_EXECUTED",
  "data_contract": {
    "dataset_id": "DS-TC-001",
    "requirements": ["usuario único", "rol autorizado"],
    "setup_method": "api",
    "cleanup_method": "api"
  },
  "evidence_required": ["screenshot", "response"],
  "automation": {
    "candidate": true,
    "reason": "flujo repetible y estable"
  },
  "derivation": {
    "method": "acceptance-criterion",
    "source_rule_ids": ["BR-USERS-001"]
  },
  "tags": ["users", "smoke"]
}
```

Usar `scripts/validate_cases.py` antes de publicar o automatizar.

## Formato manual legible

Mantener el JSON canónico como fuente estructurada y generar además una representación para testers con `scripts/render_manual_cases.py`.

Usar este formato:

```text
[CASO DE PRUEBA 01]
ID: FE-TC-001
Capa: Frontend
Feature ID: auth.login
Familia: happy-path
Reglas de negocio: BR-AUTH-001
Título: Validación de inicio de sesión exitoso
Precondiciones:
- El usuario debe estar registrado en el sistema.
Pasos:
1. Abrir la página de login.
2. Ingresar un correo válido.
3. Ingresar una contraseña válida.
4. Hacer clic en el botón "Entrar".
Resultado Esperado: El sistema muestra la bienvenida y el panel principal.
Resultado Real: Pendiente
Estado: No ejecutado
--------------------------------------------------
```

Permitir múltiples precondiciones y agregar datos, evidencia y fuentes después de los campos principales cuando existan. Mantener el mismo orden y no reemplazar los pasos observables por descripciones genéricas.

Al generar casos, inicializar:

- `actual_result`: `Pendiente`.
- `status`: `NOT_EXECUTED`.

Después de una ejecución, actualizar ambos campos con evidencia. Mostrar `PASSED` como `Pass`, `FAILED` como `Fail`, `BLOCKED` como `Blocked` y `SKIPPED` como `Skipped` en la representación manual.

## Cobertura obligatoria por capas

Usar `frontend` y `backend` como capas requeridas por defecto cuando ambas existan en el producto o en el alcance solicitado. Tratar `backend` como API, servicios, reglas, persistencia, eventos e integraciones.

Diseñar en pasadas separadas:

1. Inventariar flujos y asignar un `feature_id` estable.
2. Crear casos `frontend` para navegación, controles, validaciones visibles, estados, roles, accesibilidad y errores.
3. Crear casos `backend` para contratos, validaciones del servidor, autenticación, autorización, reglas, persistencia, idempotencia e integraciones.
4. Crear casos `e2e` para los recorridos críticos que atraviesen UI, API y datos.
5. Construir una matriz `feature_id × layer` y resolver cada celda como `covered`, `blocked` o `not-applicable`.

No usar un único caso genérico para representar ambas capas. Crear IDs independientes como `FE-TC-001`, `BE-TC-001` y `E2E-TC-001`, vinculados mediante el mismo `feature_id` y, cuando corresponda, el mismo `dataset_id`.

Guardar preferentemente:

```text
qa-artifacts/test-cases/
├── frontend.json
├── backend.json
├── e2e.json
└── coverage.json
```

Antes de terminar, ejecutar:

```bash
python scripts/validate_cases.py cases.json \
  --require-layers frontend backend \
  --require-scenarios happy-path unhappy-path boundary \
  --strict
```

La entrega debe mostrar conteos por capa. Si una capa no tiene casos, exigir en `coverage.blocked_layers` un estado `BLOCKED_*` y un motivo verificable. Si la capa realmente no existe, registrar `NOT_APPLICABLE` con evidencia del alcance. Nunca omitirla silenciosamente.

## Cobertura integral por familias y reglas

Leer [comprehensive-coverage.md](comprehensive-coverage.md) antes de diseñar. Construir primero el modelo de actores, entidades, estados, decisiones e invariantes; no empezar copiando pasos visibles sin entender el resultado de negocio.

Para cada `feature_id × layer` aplicable, exigir al menos:

- `happy-path`
- `unhappy-path`
- `boundary`

Agregar `alternate-path`, `state-transition`, `authorization`, `data-integrity`, `contract`, `integration`, `resilience`, `concurrency`, `time`, `calculation`, `search-listing`, `accessibility`, `compatibility`, `performance` y `audit-observability` cuando la dimensión exista en el dominio.

Mantener una matriz `feature_id × layer × scenario_family` y otra `business_rule_id × case_id`. Cada celda debe quedar `covered`, `BLOCKED_*` o `NOT_APPLICABLE` con evidencia.

Ejecutar:

```bash
python scripts/validate_cases.py cases.json \
  --require-layers frontend backend \
  --require-scenarios happy-path unhappy-path boundary \
  --strict
```

La cantidad de casos crece por comportamientos, oracles o riesgos distintos. No duplicar un caso cambiando valores dentro de la misma partición ni combinar varias fallas independientes en un único caso.

## Diseño manual

Crear casos:

- Positivos.
- Alternativos válidos.
- Negativos.
- Límites y equivalencias.
- Estado y transiciones.
- Roles y permisos.
- Errores y recuperación.
- Integraciones.
- Accesibilidad básica.
- Concurrencia cuando sea relevante.
- Tiempo, cálculos, auditoría y resiliencia cuando sean relevantes.

Redactar pasos observables y resultados verificables. Evitar “funciona correctamente”.

Para ejecución manual, entregar:

- Datos y credenciales mediante canal seguro.
- Identificadores de registros creados.
- Pasos de setup y cleanup.
- Evidencia requerida.
- Campos de resultado: `PASSED`, `FAILED`, `BLOCKED`, `SKIPPED`.

## Selección para automatización

Priorizar casos:

- Repetitivos.
- Críticos.
- Deterministas.
- Con alto costo manual.
- Ejecutados en cada release.
- Con precondiciones automatizables.

No automatizar sin revisar:

- Flujos visuales subjetivos.
- Escenarios de uso excepcional.
- Funcionalidades muy inestables.
- Casos sin oracle confirmado.
- Flujos sin datos o ambiente controlable.

## Priorización por riesgo

Calcular de forma explicable:

```text
score = impacto × probabilidad × frecuencia × detectabilidad
```

Documentar escala y supuestos. No presentar el score como una verdad objetiva.

## Trazabilidad

Mantener vínculos:

```text
work item o user story
  -> criterio de aceptación
  -> requisito o evidencia
  -> regla de negocio
  -> familia de escenario y técnica de derivación
  -> caso
  -> dataset
  -> automatización
  -> ejecución
  -> evidencia
  -> defecto
```

Registrar versiones de cada nodo. No reutilizar IDs para contenidos conceptualmente distintos.

Cuando el origen sea un tablero:

- Usar una referencia estable como `JIRA:ABC-123`, `ADO:4567` o el identificador nativo equivalente.
- Conservar URL, fecha de lectura y versión o `updated_at` en `qa-knowledge/work-items.json`.
- Vincular casos frontend, backend y E2E mediante el mismo `feature_id` y `work_item_ids`.
- Convertir cada criterio de aceptación en una o más verificaciones observables.
- Agregar negativos, permisos, errores y límites aunque la historia solo describa el happy path; marcar estos casos como derivados y registrar su confianza.
- No convertir comentarios informales o el estado `Done` en oracle confirmado sin evidencia adicional.

## Calidad del caso

Antes de aprobar un caso, comprobar:

- ID único.
- `feature_id` y capa definidos.
- `scenario_family`, `business_rule_ids` y dimensiones definidos.
- Objetivo y riesgo claros.
- Fuente y confianza.
- Work item o user story vinculada cuando aplique.
- Precondiciones realizables.
- Datos definidos.
- Pasos ordenados.
- Resultados observables.
- Cleanup posible o excepción documentada.
- Etiquetas y prioridad.
- Candidato a automatización justificado.
- Cobertura frontend y backend satisfecha, bloqueada o no aplicable de forma explícita.
- Happy, unhappy y boundary cubiertos por capa, o excepción explícita.
- Estados, roles, decisiones y riesgos del modelo cubiertos o bloqueados.
- Ausencia de duplicados semánticos dentro de la misma partición.
