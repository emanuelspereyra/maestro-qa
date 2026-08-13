# Preflight, ejecución y defectos

## Contenido

- Preflight
- Archivos de ambiente
- Selección de ambiente
- Catálogo de rutas
- Ciclo por caso
- Cierre y consultas de verificación
- Ejecución manual
- Defectos y severidad
- Versiones
- Publicación

## Preflight

Validar antes de una suite:

- Ambiente permitido y versión.
- Frontend y API accesibles.
- Variables de entorno requeridas presentes.
- Usuario y roles.
- Base y permisos.
- Servicios externos y modo efectivo: sandbox real, mock contractual, fixture o bloqueo.
- Navegadores y runtimes.
- Dataset generable.
- Cleanup disponible.
- Espacio para evidencias.

No imprimir valores secretos. Registrar solo presencia o ausencia.

Estados:

- `READY`
- `BLOCKED_ENVIRONMENT`
- `BLOCKED_AUTH`
- `BLOCKED_DATA_SETUP`
- `BLOCKED_RUNTIME`
- `BLOCKED_DEPENDENCY`
- `BLOCKED_PREFLIGHT`

No ejecutar el caso cuando una dependencia obligatoria esté bloqueada.

## Archivos de ambiente

Auditar `.gitignore` con `scripts/gitignore_manager.py` y `.env` con `scripts/env_file_manager.py` antes del preflight. Bloquear publicación si Git ya sigue archivos sensibles. El preflight puede cargar un archivo sin evaluación de shell:

```bash
python scripts/preflight.py \
  --env-file .env \
  --require-env-file \
  --require-route-catalog \
  --require-frontend \
  --require-api
```

Exigir que `.env`:

- Exista en el proyecto que se ejecutará.
- Esté ignorado por Git.
- Tenga permisos `0600`.
- No conserve placeholders en variables requeridas.

Las variables ya presentes en el proceso prevalecen sobre `.env`. No registrar valores ni cargarlos de un proyecto a otro. Leer [environment-files.md](environment-files.md) para auditoría, creación y provisión segura.

## Selección de ambiente

Separar el ambiente usado para descubrir o diseñar los casos del ambiente donde se ejecutan. No guardar URLs, usuarios ni conexiones dentro de los casos automatizados.

Usar:

```text
QA_TARGET_ENV=dev
QA_ALLOWED_ENVIRONMENTS=dev,main,qa,staging

QA_DEV_FRONTEND_URL=https://dev.example.test
QA_DEV_API_BASE_URL=https://api.dev.example.test

QA_MAIN_FRONTEND_URL=https://main.example.test
QA_MAIN_API_BASE_URL=https://api.main.example.test
```

Ejemplo de ejecución:

```bash
export QA_TARGET_ENV=main
export QA_ALLOWED_ENVIRONMENTS=dev,main,qa,staging
export QA_MAIN_FRONTEND_URL=https://main.example.test
export QA_MAIN_API_BASE_URL=https://api.main.example.test

python scripts/preflight.py \
  --require-route-catalog \
  --require-frontend \
  --require-api
pytest
```

Al ejecutar con `QA_TARGET_ENV=main`, resolver únicamente variables con prefijo `QA_MAIN_`. Para un ambiente `feature-01`, normalizar el prefijo a `QA_FEATURE_01_`.

Variables admitidas por perfil:

- `FRONTEND_URL`
- `API_BASE_URL`
- `TEST_USERNAME`
- `TEST_PASSWORD`
- `DB_READ_CONNECTION`
- `DB_WRITE_CONNECTION`
- Variables adicionales documentadas por el proyecto.

Permitir variables genéricas como `QA_FRONTEND_URL` o `QA_API_BASE_URL` únicamente cuando `QA_ALLOW_GENERIC_ENV_FALLBACK=true`. Esto evita ejecutar accidentalmente contra un ambiente distinto.

Bloquear ambientes no incluidos en `QA_ALLOWED_ENVIRONMENTS`. Bloquear `prod` y `production` salvo que `QA_ALLOW_PRODUCTION=true`, y mantener las restricciones adicionales de escritura, carga y acciones irreversibles.

Ejecutar el preflight para cada cambio de `QA_TARGET_ENV`. Registrar el ambiente efectivo en reportes, evidencias, datasets, defectos e historial.

El argumento `--environment` puede sobrescribir `QA_TARGET_ENV` para una única invocación del preflight o de `db_tool.py`. Si se omite, ambos utilizan `QA_TARGET_ENV`.

Para aprovisionamiento por base, `db_tool.py` resuelve por defecto `QA_<AMBIENTE>_DB_READ_CONNECTION` o `QA_<AMBIENTE>_DB_WRITE_CONNECTION`. Una escritura requiere además `QA_ALLOW_DB_WRITE=true`, `--execute`, `--allow-write` y que el ambiente figure en `QA_ALLOWED_DB_WRITE_ENVIRONMENTS`. `main` no queda habilitado para escritura automáticamente.

## Catálogo de rutas

Mantener `qa-knowledge/environment-routes.json` como inventario auditable de URLs por ambiente. Obtener candidatos mediante `scripts/discover_environment_routes.py`, revisar sus fuentes y actualizar los estados a `documented` o `verified` antes de ejecutar.

Ejecutar:

```bash
python scripts/preflight.py \
  --require-route-catalog \
  --require-frontend \
  --require-api
```

El preflight debe bloquear cuando:

- El ambiente no existe en el catálogo.
- Falta una ruta requerida.
- La ruta sigue como `candidate`, `missing`, `conflict` o `access-blocked`.
- La variable de ejecución no coincide con la URL documentada.
- La URL base incluye credenciales, query o fragmento.

Una URL documentada pero no accesible conserva su evidencia, aunque la ejecución queda `BLOCKED_PREFLIGHT`. No reemplazarla por una URL inferida.

## Ciclo por caso

```text
preflight
  -> setup
  -> execute
  -> verify
  -> evidence
  -> defect preview
  -> generate verification queries
  -> cleanup
  -> history
```

Registrar un evento por etapa material. El cleanup debe intentarse incluso después de un fallo, sin borrar evidencia.

## Cierre y consultas de verificación

Al finalizar la ejecución funcional, antes del cleanup, ejecutar `scripts/generate_verification_queries.py` para cada dataset realmente usado. Guardar los artefactos bajo `qa-artifacts/data/verification/<run_id>/` y enlazar su manifest desde el historial y el reporte final.

Las consultas deben ser solo lectura, proyectar campos no sensibles y tener filtros por `qa_run_id` o identificadores exactos. Dejarlas como `GENERATED_NOT_EXECUTED`; no usar credenciales de escritura ni ejecutarlas por defecto.

Registrar si el cleanup quedó `COMPLETED`, `DEFERRED_WITH_EXPIRY`, `FAILED` o `NOT_APPLICABLE`. Si fue completado, el query de conteo permite verificar que no queden residuos. Diferir el cleanup únicamente con autorización, fecha de expiración y responsable; no dejar datos indefinidamente solo para facilitar inspección.

Si una suite usó un mock externo, incluir `MOCKED_DEPENDENCY`, servicio, escenario y versión contractual en el resumen. Su resultado no reemplaza la suite contra sandbox real.

## Ejecución manual

Preparar:

- Pasos.
- Dataset.
- Usuario/rol.
- IDs de registros.
- Oracle.
- Evidencia requerida.

Permitir resultado `PASSED`, `FAILED`, `BLOCKED` o `SKIPPED` y comentario. Sanitizar adjuntos antes de publicarlos.

## Defectos

Crear un borrador con:

- Título.
- Caso y fuente.
- Ambiente y versiones.
- Precondiciones.
- Datos usados.
- Pasos.
- Resultado esperado.
- Resultado obtenido.
- Reproducibilidad.
- Severidad sugerida.
- Evidencia.

Buscar duplicados por funcionalidad, síntoma, endpoint y versión. No cerrar ni editar defectos existentes sin pedido explícito.

Mostrar preview antes de una escritura externa.

## Severidad

- Critical: pérdida grave, seguridad o indisponibilidad crítica.
- High: flujo principal bloqueado sin workaround.
- Medium: degradación con workaround.
- Low: impacto menor o cosmético.

Separar severidad técnica de prioridad de negocio.

## Versiones

Registrar cuando estén disponibles:

- Release.
- Commit frontend.
- Commit backend.
- Versión de esquema.
- Versión del caso.
- Hash o versión del test.
- Ambiente, navegador, runtime y herramienta.

Usar esta información para impacto y tendencias, no para adivinar causalidad.

## Publicación

Para Jira/Xray, Zephyr, TestRail, Azure DevOps u otro:

1. Resolver proyecto y tipo.
2. Mapear campos.
3. Buscar duplicados.
4. Mostrar preview.
5. Confirmar escritura.
6. Publicar.
7. Registrar ID remoto o error sanitizado.
