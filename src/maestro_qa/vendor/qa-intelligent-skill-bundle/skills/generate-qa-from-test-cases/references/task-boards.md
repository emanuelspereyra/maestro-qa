# Tableros de tareas y user stories

## Objetivo

Aprender requisitos, alcance y riesgos desde un tablero autorizado y convertirlos en conocimiento QA trazable. Usar acceso de solo lectura por defecto.

## Onboarding

Preguntar de a una:

1. Si existe acceso a un tablero, backlog o user stories.
2. Proveedor: Jira, Azure DevOps Boards, Linear, GitHub Issues/Projects u otro.
3. URL, proyecto o espacio y tablero.
4. Alcance autorizado: sprint, release, épica, filtro, consulta o IDs explícitos.
5. Tipos incluidos: épica, feature, user story, tarea y bug.
6. Si comentarios y adjuntos pueden leerse.
7. Método de autenticación y si ya está configurado.

No pedir tokens, contraseñas, cookies ni URLs con credenciales. Guardar solo el método y el nombre de la variable cuando corresponda.

## Verificación y permisos

- Verificar una lectura no mutante del proyecto y alcance correctos antes de registrar `VERIFIED`.
- Si falla, clasificar `not_found`, `authentication`, `authorization`, `network` o `unsupported` y registrar `BLOCKED_TASK_BOARD_ACCESS`.
- Continuar con documentación, código, frontend, API o base aunque el tablero quede bloqueado.
- Mantener `write_enabled: false` por defecto.
- Exigir preview y autorización antes de crear o modificar tareas, comentarios, estados, casos o defectos.
- No recorrer toda la organización cuando se autorizó únicamente un proyecto o sprint.

## Información a extraer

Por cada work item, conservar solo lo necesario:

- ID nativo, proveedor, tipo, título y URL.
- Proyecto, tablero, sprint, release y jerarquía.
- Estado, prioridad, etiquetas, componentes y responsables solo cuando aporten contexto QA.
- Descripción y criterios de aceptación por separado.
- Dependencias, bloqueos, historias relacionadas y bugs vinculados.
- Referencias a documentación, diseño, API o repositorios.
- Autor y fecha de comentarios que registren una decisión; evitar conversaciones irrelevantes.
- Metadatos de adjuntos permitidos; no copiar archivos sensibles sin necesidad.
- `created_at`, `updated_at`, fecha de lectura y versión disponible.

No guardar secretos, PII innecesaria, cookies, encabezados de autorización ni contenido completo que no sea necesario para diseñar pruebas.

## Confianza y reconciliación

- Tratar criterios de aceptación aprobados como evidencia de requisito.
- Tratar descripciones, comentarios y estados como evidencia contextual con confianza explícita.
- No interpretar `Done`, `Closed` o equivalentes como prueba aprobada.
- No asumir que una user story cubre negativos, permisos, errores o límites.
- Contrastar tablero, documentación, código, API y comportamiento observado.
- Registrar contradicciones y solicitar decisión cuando cambien el oracle.

## Conocimiento normalizado

Guardar `qa-knowledge/work-items.json` con una estructura equivalente a:

```json
{
  "schema_version": 1,
  "generated_at": "2026-08-03T00:00:00Z",
  "source": {
    "provider": "jira",
    "project": "ABC",
    "board": "Producto",
    "scope_type": "sprint",
    "scope_value": "Sprint 42",
    "access_status": "verified"
  },
  "work_items": [
    {
      "ref": "JIRA:ABC-123",
      "type": "user-story",
      "title": "Crear usuario",
      "url": "https://example.invalid/browse/ABC-123",
      "state": "Ready for QA",
      "priority": "high",
      "parent_refs": ["JIRA:ABC-100"],
      "acceptance_criteria": [
        {"text": "El usuario se crea con un correo único", "confidence": "confirmed"}
      ],
      "linked_bug_refs": [],
      "updated_at": "",
      "fetched_at": "",
      "confidence": "confirmed"
    }
  ]
}
```

Usar dominios de ejemplo en plantillas; no guardar URLs ficticias como evidencia real.

## Generación de casos

- Derivar `feature_id` estable desde la capacidad, no desde el número de sprint.
- Guardar `work_item_ids` en cada caso relacionado.
- Crear casos frontend y backend separados cuando ambas capas existan; sumar E2E para integración crítica.
- Convertir cada criterio de aceptación en verificaciones observables.
- Leer [comprehensive-coverage.md](comprehensive-coverage.md), modelar las reglas y asignar IDs `BR-*` antes de expandir escenarios.
- Agregar happy path, alternativas válidas, unhappy path y boundary aunque no estén enumerados en la historia; marcarlos como derivados cuando corresponda.
- Agregar transiciones, permisos, integridad, contratos, resiliencia, concurrencia, tiempo, cálculos, integraciones y auditoría cuando la historia o el producto expongan esas dimensiones.
- Mantener matrices `work_item -> business_rule -> feature_id -> layer -> scenario_family -> case_id`.
- Propagar prioridad y riesgo solo con una regla explicable; no copiarlos mecánicamente.
- Detectar historias sin oracle, datos, permisos o ambiente y marcarlas `PENDING` o `BLOCKED_*`.

## Actualización incremental

En lecturas posteriores:

1. Comparar ID y `updated_at` o versión.
2. Actualizar únicamente los items modificados.
3. No sobrescribir reglas confirmadas de forma silenciosa.
4. Marcar casos potencialmente obsoletos cuando cambie un criterio de aceptación.
5. Registrar el cambio y los artefactos afectados en el historial.
