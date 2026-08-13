# Exploración inteligente y cobertura integral

## Objetivo

Maximizar la cantidad de casos útiles sin inflar la suite con duplicados ni inventar requisitos. Modelar primero la lógica de negocio y derivar después escenarios atómicos, trazables y verificables.

No prometer todas las combinaciones matemáticamente posibles. Cubrir todas las reglas, estados, transiciones, roles, capas y familias de riesgo relevantes; usar pairwise o priorización por riesgo cuando el producto cartesiano no sea ejecutable.

## Modelo de negocio previo

Antes de redactar casos, construir `qa-knowledge/business-model.json` con:

- Actores, roles, ownership, tenant y permisos.
- Entidades, atributos, relaciones, unicidad y ciclo de vida.
- Estados válidos, estado inicial y terminal, transiciones, guardas y acciones prohibidas.
- Reglas, invariantes, decisiones, fórmulas, redondeos, moneda, impuestos y acumuladores.
- Restricciones de fecha, hora, zona horaria, vencimiento, ventanas y periodicidad.
- Dependencias, integraciones, eventos, colas, notificaciones y efectos secundarios.
- Límites funcionales, cuotas, tamaños, paginación, orden, filtros y búsquedas.
- Auditoría, historial, reversión, reintentos, idempotencia y recuperación.

Asignar IDs estables como `BR-<dominio>-NNN` a cada regla. Registrar fuente, confianza y contradicciones. Una regla inferida puede generar un caso con `confidence: pending`, pero no un oracle confirmado.

## Pasadas de descubrimiento

Realizar todas las pasadas aplicables y registrar las que queden bloqueadas:

1. **Inventario:** enumerar módulos, rutas, endpoints, comandos, procesos programados y entradas externas.
2. **Flujo nominal:** recorrer el happy path de cada actor y resultado de negocio.
3. **Alternativas válidas:** buscar caminos equivalentes, acciones opcionales, cancelación, regreso, edición y reanudación.
4. **Validaciones:** variar un dato por vez y observar reglas visibles y del servidor.
5. **Estados:** recorrer cada transición válida e intentar transiciones inválidas, repetidas, fuera de orden y desde estados terminales.
6. **Roles:** repetir acciones por rol, ownership, tenant, sesión anónima, expirada o revocada.
7. **Datos:** probar particiones válidas e inválidas, nulos, vacíos, duplicados, relaciones inexistentes y límites.
8. **Integraciones:** simular éxito, rechazo, timeout, respuesta parcial, duplicada, tardía o fuera de orden cuando exista un mecanismo autorizado.
9. **Concurrencia:** analizar doble envío, solicitudes simultáneas, edición conflictiva, locks, idempotencia y consistencia.
10. **Tiempo:** revisar fechas mínimas/máximas, medianoche, fin de mes/año, horario de verano, expiración y reintentos.
11. **Recuperación:** refresh, back/forward, pérdida de red, reautenticación, retry, rollback y continuación segura.
12. **No funcional funcionalizable:** accesibilidad, responsividad, localización, compatibilidad, volumen y tiempos con oracle definido.

Después de cada pasada, actualizar reglas, preguntas, riesgos, mapa de flujos y candidatos de casos. No repetir una acción peligrosa solo para aumentar cobertura.

## Señales de lógica de negocio

### Con código

Buscar condiciones, guards, políticas, validators, enums, máquinas de estado, constraints, índices únicos, ramas de error, feature flags, cálculos, transacciones, retries, eventos y tests existentes. Relacionar cada rama relevante con una regla y un escenario.

No considerar el código como especificación correcta: usarlo para descubrir decisiones y contrastarlas con requisitos y comportamiento.

### Sin código

Inferir candidatos desde:

- Controles habilitados o deshabilitados según estado o rol.
- Campos condicionales, defaults, máscaras, tooltips, mensajes y confirmaciones.
- Cambios de menú, acciones y datos entre usuarios.
- Códigos de respuesta, campos, validaciones y secuencia del tráfico API autorizado.
- Estados vacíos, loaders, errores, reintentos, paginación y comportamiento tras refresh.
- Diferencias entre crear, consultar, editar, cancelar, archivar, restaurar y eliminar.

Variar una dimensión por vez para identificar causa y efecto. Registrar la hipótesis como `inferred`, buscar corroboración y solicitar confirmación si cambia el resultado esperado.

## Familias de escenarios

Clasificar cada caso con una sola `scenario_family` principal y varias `coverage_dimensions` secundarias.

Familias permitidas:

- `happy-path`: recorrido principal válido.
- `alternate-path`: variante válida u opcional.
- `unhappy-path`: entrada, acción o condición inválida.
- `boundary`: mínimo, máximo, justo debajo, justo encima y particiones equivalentes.
- `state-transition`: transición válida, inválida, repetida o fuera de orden.
- `authorization`: rol, permiso, ownership, tenant y sesión.
- `data-integrity`: unicidad, relación, consistencia, persistencia y cleanup.
- `contract`: request, response, schema, headers, códigos y compatibilidad.
- `integration`: dependencia externa, evento, cola, webhook o notificación.
- `resilience`: timeout, retry, caída, respuesta parcial, rollback y recuperación.
- `concurrency`: carrera, doble envío, lock, conflicto e idempotencia.
- `time`: fecha, hora, zona, vencimiento y ventanas.
- `calculation`: fórmula, redondeo, moneda, impuestos, totales y precisión.
- `search-listing`: búsqueda, filtro, orden, paginación y estados vacíos.
- `accessibility`: teclado, foco, nombre accesible, contraste y anuncios esenciales.
- `compatibility`: navegador, viewport, locale, encoding o versión soportada.
- `performance`: volumen, throughput, latencia, soak, spike y degradación.
- `audit-observability`: historial, actor, timestamp, correlación, log y evidencia.

El perfil integral exige al menos `happy-path`, `unhappy-path` y `boundary` por cada `feature_id × layer` aplicable. Las demás familias se vuelven obligatorias cuando el modelo del negocio detecta la dimensión correspondiente. Registrar `NOT_APPLICABLE` o `BLOCKED_*` con motivo y evidencia; no omitirlas silenciosamente.

## Técnicas de derivación

Aplicar según la forma de la regla:

- Particiones de equivalencia y valores límite para campos y cuotas.
- Tablas de decisión para combinaciones de condiciones y resultados.
- Transición de estados para ciclos de vida y acciones condicionadas.
- Causa-efecto para reglas con varias precondiciones.
- Matriz actor × acción × estado × ownership para autorización.
- Matriz CRUD × entidad × relación para integridad y ciclo completo.
- Recorridos modelo-basados para caminos entre nodos, estados y capas.
- Pairwise para combinaciones independientes de gran cardinalidad.
- Property-based o propiedades metamórficas cuando existe una propiedad verificable pero no un ejemplo único.
- Error guessing basado en fallas históricas, defectos, logs y zonas de cambio.

No usar pairwise para descartar combinaciones explícitamente prohibidas, de alto riesgo o vinculadas a dinero, permisos, persistencia o seguridad.

## Construcción de casos

Crear un caso por comportamiento y oracle principal. Evitar casos enormes con múltiples fallas independientes y evitar duplicados que solo cambien datos de la misma partición.

Cada caso debe contener:

- `scenario_family`, `business_rule_ids` y `coverage_dimensions`.
- Fuente y confianza de la regla u oracle.
- Actor, estado inicial, acción, datos, resultado observable y estado final.
- Capa, `feature_id`, `work_item_ids`, dataset, setup, cleanup y evidencia.
- Método de derivación: criterio, tabla de decisión, límite, transición, pairwise, propiedad o riesgo histórico.

Separar frontend, backend y E2E. Para un mismo riesgo, crear casos por capa cuando el oracle de cada capa sea distinto; no duplicar texto cambiando solo la etiqueta.

## Cobertura y saturación

Mantener `qa-artifacts/test-cases/coverage.json` con:

- Matriz `feature_id × layer × scenario_family`.
- Reglas cubiertas, bloqueadas, pendientes y sin casos.
- Estados y transiciones cubiertos.
- Roles y permisos cubiertos.
- Decisiones y combinaciones seleccionadas.
- Riesgos y defectos históricos cubiertos.
- Fuentes no accesibles y efecto sobre la completitud.

Detener la expansión cuando se cumplan simultáneamente:

1. Todas las reglas y criterios tienen al menos un caso o un bloqueo explícito.
2. Las familias obligatorias están cubiertas por capa.
3. Los estados, transiciones, roles y decisiones relevantes están resueltos.
4. Una nueva pasada solo produce duplicados o variaciones dentro de una partición ya cubierta.
5. Los riesgos residuales y supuestos pendientes están documentados.

Ejecutar la compuerta:

```bash
python scripts/validate_cases.py cases.json \
  --require-layers frontend backend \
  --require-scenarios happy-path unhappy-path boundary \
  --strict
```

Entregar conteos por capa, familia, regla y feature, además de bloqueos y riesgos residuales.
