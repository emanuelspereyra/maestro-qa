# Performance, carga y estrés

## Precondiciones

No generar umbrales ficticios. Solicitar o marcar como pendientes:

- Objetivo del ensayo.
- Ambiente autorizado.
- Tráfico esperado.
- Usuarios concurrentes o tasa de llegada.
- Duración y fases.
- SLA y percentiles.
- Error rate permitido.
- Límites de infraestructura.
- Datos y cuentas.
- Ventana de ejecución.
- Contacto responsable.

No ejecutar carga en producción salvo autorización explícita, coordinación operativa y límites aprobados.

Seleccionar el target con `QA_TARGET_ENV` y resolver `QA_<AMBIENTE>_API_BASE_URL` antes de generar o ejecutar el comando. El escenario no debe conservar una URL de `dev` fija. Registrar el ambiente efectivo en el reporte de carga.

## Derivar escenarios

Usar casos funcionales para identificar:

- Flujos críticos.
- Mezcla de transacciones.
- Dependencias y correlación.
- Think time.
- Setup y cleanup.
- Datos únicos o reutilizables.

No traducir cada caso funcional a carga. Elegir recorridos representativos del uso real.

## Tipos de prueba

- Baseline: referencia con carga baja.
- Load: volumen esperado.
- Stress: superar capacidad de forma controlada.
- Spike: incremento abrupto.
- Endurance: degradación prolongada.
- Volume: grandes cantidades de datos.

## Artillery

Artillery requiere Node.js. Python puede generar YAML, CSV/JSON y comandos, pero no reemplaza el runtime.

Generar:

- `config.target`.
- Fases.
- Escenarios ponderados.
- Variables y payloads.
- Captura y correlación.
- Thresholds confirmados.
- Comando reproducible.

Pasar el target ya resuelto a Artillery mediante una variable del proceso o `--target`; no duplicar URLs por ambiente dentro del escenario.

No ejecutar si Node.js o Artillery no están disponibles. Marcar `BLOCKED_RUNTIME`.

## Locust

Usar Locust cuando se requiera runtime Python. Generar tareas ponderadas, wait time, autenticación, datos y eventos de validación.

Resolver el host con el mismo perfil `QA_TARGET_ENV` usado por pytest y pasarlo a Locust sin fijarlo en el `locustfile`.

## Resultados

Registrar:

- Versión y ambiente.
- Perfil de carga real.
- Requests, errores y throughput.
- p50, p90, p95 y p99 cuando existan.
- Saturación o métricas externas disponibles.
- Umbrales aprobados y resultado.
- Artefactos originales.

No declarar causa raíz solo por correlación. Separar observación, hipótesis y evidencia.
