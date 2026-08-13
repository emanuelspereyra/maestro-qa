# Historial y tablero

## Modelo

Usar un `run_id` por ejecución. Escribir:

- `qa-history/events.jsonl`: fuente append-only.
- `qa-history/qa-history.db`: consultas y tablero.
- `qa-history/runs/<run_id>.json`: resumen.

No eliminar historial durante cleanup.

## Evento

Registrar:

- `event_id`
- `timestamp_utc`
- `run_id`
- `project`
- `module`
- `action`
- `target`
- `status`
- `duration_ms`
- `case_id`
- `dataset_id`
- `summary`
- `artifact_path`
- `error_code`
- `metadata` sanitizada

Usar `scripts/qa_history.py`.

## Sanitización

Redactar claves o valores asociados a:

- password
- secret
- token
- cookie
- authorization
- credential
- connection string

No registrar bodies completos si pueden contener PII. Preferir schema, hash seguro o extracto sanitizado.

Para rutas por ambiente, registrar eventos `route-scan`, `route-documented`, `route-verified`, `route-conflict` y `route-missing`. Guardar ambiente, tipo de servicio, fuente y URL sanitizada; nunca guardar userinfo, query, fragmento ni headers.

Para `.env`, registrar `env-audit`, `env-created`, `env-incomplete`, `env-ready` y `env-blocked`. Guardar solo proyecto, archivo, template, nombres faltantes, permisos y estado de Git ignore. Exigir `values_exposed=false`.

Para `.gitignore`, registrar `gitignore-audit`, `gitignore-updated` y `tracked-sensitive`. Guardar proyecto, stacks, patrones agregados y rutas sensibles; nunca contenido ni valores. Distinguir un archivo ignorado de uno que Git ya sigue.

Para datos, registrar `dataset-generated`, `seed-planned`, `seed-inserted`, `verification-queries-generated` y `cleanup-completed`. Crear un evento por entidad y tabla o colección. Usar los estados generales `GENERATED`, `PLANNED` o `EXECUTED` y guardar `GENERATED_NOT_INSERTED`, `PLANNED_NOT_INSERTED`, `INSERTED`, `GENERATED_NOT_EXECUTED` o `CLEANED` en `metadata.data_status`. Guardar ambiente, cantidad, `dataset_id`, `run_id`, identificadores sanitizados y ruta del inventario, recibo o manifest de consultas. No incluir secretos ni PII real.

Para dependencias externas, registrar `mock-catalog-validated`, `mock-started`, `mock-scenario-used` y `mock-stopped`. Guardar servicio, modo, escenario, versión contractual y `mocked_dependency=true`; no guardar bodies, headers ni credenciales. Mantener sus resultados separados de `real-sandbox`.

## Comandos

```bash
python scripts/qa_history.py init --history-dir qa-history
python scripts/qa_history.py start-run --history-dir qa-history --project demo
python scripts/qa_history.py log --history-dir qa-history --run-id <id> \
  --module manual --action create-case --status GENERATED
python scripts/qa_history.py end-run --history-dir qa-history --run-id <id> \
  --status COMPLETED
python scripts/qa_history.py summary --history-dir qa-history
python scripts/qa_history.py export --history-dir qa-history --output events.csv
```

## Tablero

Ejecutar:

```bash
streamlit run scripts/dashboard.py -- --history-dir qa-history
```

Mostrar:

- Runs por estado.
- Timeline.
- Casos generados y ejecutados.
- Passed, failed, blocked y skipped.
- Cobertura histórica.
- Preflight y bloqueos.
- Rutas por ambiente, faltantes y conflictos.
- Estado de `.env` y variables faltantes por proyecto, sin valores.
- Estado de `.gitignore`, stacks, reglas faltantes y archivos sensibles ya versionados.
- Datos generados, planificados, insertados y limpiados por tabla o colección, con cantidad y enlace al inventario o recibo.
- Consultas de verificación generadas por run, tabla o colección, con enlace al manifest y estado de cleanup.
- Uso de APIs de terceros por modo, escenario y versión de contrato, diferenciando mock de sandbox real.
- Defectos.
- Flaky tests.
- Versiones y cambios.
- Performance.

Permitir filtros por proyecto, run, fecha, módulo, caso y estado. Mantener solo lectura.

## Retención

Definir política por proyecto. Archivar antes de eliminar. Requerir una acción explícita para cualquier borrado material.
