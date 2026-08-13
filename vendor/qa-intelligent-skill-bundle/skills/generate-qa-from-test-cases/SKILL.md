---
name: generate-qa-from-test-cases
description: Create, explore, automate, execute, and audit comprehensive QA from test cases, task boards, user stories, documentation, source code, live frontends, observed APIs, and database schemas. Use when Codex must onboard a QA project, discover business logic and risks, and maximize meaningful scenario coverage across frontend, backend, E2E, data, API, and performance. Covers happy, alternate, unhappy, boundary, state, authorization, integrity, integration, resilience, concurrency, time, calculations, accessibility, performance, controlled third-party API mocks, post-run database verification queries, secure environment setup, and auditable history.
---

# QA inteligente desde casos

## Principios

Trabajar con evidencia. Distinguir siempre entre comportamiento confirmado, inferido y pendiente de validación. No convertir el comportamiento observado en un resultado esperado sin otra evidencia.

Separar estos estados:

- `NOT_EXECUTED`: caso generado que todavía no fue ejecutado.
- `PLANNED`: propuesto, no realizado.
- `GENERATED`: artefacto creado, no ejecutado.
- `EXECUTED`: acción realizada.
- `VERIFIED`: resultado comprobado.
- `PASSED`, `FAILED`, `BLOCKED` o `SKIPPED`: resultado final.

No afirmar que una prueba fue ejecutada cuando solo se generó. No ocultar fallas mediante aserciones debilitadas, self-healing silencioso o reintentos ilimitados.

## Flujo principal

1. Buscar `qa-project.yaml` y `qa-knowledge/` en el proyecto.
2. Si falta configuración, leer [onboarding.md](references/onboarding.md), preguntar de a una y crearla con `scripts/init_qa_project.py` o copiar `assets/qa-project.template.yaml`.
3. Iniciar un `run_id` con `scripts/qa_history.py start-run`.
4. Reunir únicamente las fuentes autorizadas: casos existentes, tableros de tareas y user stories, documentación, repositorios, aplicación, API y base de datos.
5. Clasificar el trabajo como white-box, black-box o híbrido. Leer [discovery.md](references/discovery.md).
6. Construir o actualizar `qa-knowledge/` sin sobrescribir conocimiento confirmado de forma silenciosa.
7. Modelar la lógica de negocio y agotar las pasadas aplicables de [comprehensive-coverage.md](references/comprehensive-coverage.md).
8. Diseñar casos con el contrato definido en [test-design.md](references/test-design.md) y ejecutar la compuerta por capa y familia.
9. Ejecutar preflight antes de preparar datos o pruebas. Leer [execution.md](references/execution.md).
10. Generar un dataset reproducible por caso. Si depende de una API externa, decidir entre sandbox real, mock contractual, fixture sanitizado o bloqueo según [external-service-mocking.md](references/external-service-mocking.md). Leer [data.md](references/data.md).
11. Generar automatización solo para candidatos adecuados. Leer [automation.md](references/automation.md).
12. Para performance, leer [performance.md](references/performance.md) y solicitar NFR faltantes.
13. Ejecutar únicamente lo autorizado y con precondiciones satisfechas.
14. Verificar, preparar defectos y generar consultas de lectura acotadas al dataset antes del cleanup. Luego limpiar datos y registrar evidencias.
15. Actualizar historial y tablero según [audit-dashboard.md](references/audit-dashboard.md).

## Onboarding obligatorio

Si falta `qa-project.yaml`, explicarlo como primera inicialización, no como error, y continuar en la misma respuesta con la primera pregunta. No detener el turno únicamente después de informar que falta la configuración.

Preguntar primero si existe acceso al código.

- Si hay acceso, solicitar monorepo o repositorios separados, URL y rama de frontend y backend.
- Para cada repositorio, preguntar si es público o privado, el proveedor y si este entorno ya está autenticado. Si no está autenticado, ofrecer conexión mediante el conector disponible, CLI del proveedor, SSH o gestor de credenciales antes de intentar descargarlo.
- No pedir contraseñas, tokens, claves privadas ni URLs con secretos en el chat. Solicitar únicamente el método de autenticación y, cuando corresponda, el nombre de la variable de entorno que ya contiene la credencial.
- Validar obligatoriamente con `scripts/verify_repository.py` o `git ls-remote` sin prompts antes de clonar. Registrar `VERIFIED` solo si el repositorio y la rama responden.
- Si la validación devuelve `authentication` o `authorization`, detener la clonación, pedir que el usuario complete la conexión y repetir la validación. Si decide no conectarse, marcar la fuente como `BLOCKED_SOURCE_ACCESS` y ofrecer carpeta local, ZIP o modo black-box.
- Clonar únicamente los repositorios validados e inspeccionarlos inicialmente en modo lectura. No afirmar que existe acceso al código por recibir solamente una URL.
- Si no hay acceso, continuar en modo black-box y posponer cualquier pedido de URL hasta revisar la documentación y el catálogo de rutas.

Preguntar después si existe documentación.

- Si existe, solicitar enlaces o archivos PDF, Word, sitio web, OpenAPI, Postman, wiki o diagramas.
- Si una fuente no abre, indicar cuál falló y por qué. Solicitar exportación, adjunto o permiso, y continuar con las demás fuentes.

Preguntar después si existe un tablero de tareas, backlog o user stories.

- Si existe, leer [task-boards.md](references/task-boards.md) y solicitar proveedor, URL, proyecto o espacio, tablero y alcance autorizado: sprint, release, épica, filtro o consulta.
- Preguntar si el entorno ya está autenticado y qué mecanismo seguro se usará. No pedir tokens, contraseñas ni cookies en chat; guardar solo el método y el nombre de la variable cuando corresponda.
- Verificar acceso en modo lectura antes de aprender del tablero. Si falla, registrar `BLOCKED_TASK_BOARD_ACCESS`, informar la causa y continuar con las demás fuentes.
- Importar únicamente los work items autorizados y normalizarlos en `qa-knowledge/work-items.json`; conservar ID, URL, versión o fecha de lectura y relaciones.
- Tratar criterios de aceptación aprobados como evidencia de requisito. Tratar descripciones, comentarios y estados como evidencia contextual cuya confianza debe registrarse; `Done` no demuestra que una prueba pasó.
- No modificar tareas, estados, comentarios, casos o defectos sin preview y autorización explícita.

Antes de pedir rutas de ambientes:

- Reunir los alias autorizados y buscar primero en `qa-project.yaml`, `qa-knowledge/environment-routes.json`, documentación, OpenAPI, variables de Postman, repositorios, CI/CD, manifiestos de despliegue y configuración pública de ejemplo.
- Para fuentes locales, usar `scripts/discover_environment_routes.py` y revisar sus candidatos; no tratarlos como confirmados automáticamente.
- Construir un catálogo por ambiente con frontend, API y, cuando apliquen, autenticación, administración, OpenAPI y servicios adicionales.
- Verificar cada URL de forma no destructiva. Si está documentada y es consistente, no volver a pedirla.
- Preguntar de a una únicamente las rutas ausentes, contradictorias, inaccesibles o vencidas, indicando ambiente y servicio exactos.
- No derivar `main`, `qa` o `staging` sustituyendo texto dentro de una URL de `dev`.
- Guardar fuente, estado y variable `QA_<AMBIENTE>_<SETTING>` en `qa-knowledge/environment-routes.json`.

Después de obtener cada proyecto local, auditar su configuración:

- Leer [gitignore.md](references/gitignore.md) y ejecutar `scripts/gitignore_manager.py` primero sin `--apply` para frontend, backend, automatización y performance.
- Mostrar los stacks, archivos sensibles candidatos y patrones faltantes. Después aplicar únicamente el bloque administrado, conservando todas las reglas existentes.
- No agregar patrones amplios como `*.json` o `*.csv`. Mantener versionados `qa-project.yaml`, `qa-knowledge/` y los `.env.example`, `.env.sample` o `.env.template` sanitizados.
- Si Git ya sigue un archivo sensible, marcar `BLOCKED_TRACKED_SENSITIVE`. `.gitignore` no lo retira del índice ni del historial: no ejecutar automáticamente `git rm`, reescritura de historial ni rotación.
- Leer [environment-files.md](references/environment-files.md) y ejecutar `scripts/env_file_manager.py` primero sin mutaciones.
- Verificar frontend, backend y automatización por separado. Detectar `.env`, examples y variables referenciadas por el código.
- Usar los valores de `.env` solo dentro del proceso autorizado. Nunca mostrarlos, copiarlos al chat ni registrarlos; reportar únicamente nombres y estados.
- Si falta `.env`, crear uno desde el example del mismo proyecto con `--create` después de verificar que el bloque administrado lo ignore. No sobrescribir archivos existentes, no copiar secretos del example y usar permisos `0600`.
- Si no existe example, crear un archivo mínimo con nombres descubiertos y placeholders vacíos.
- Resolver primero variables no secretas desde documentación y el catálogo de rutas. Preguntar solo las que sigan faltando.
- Para contraseñas, tokens, claves y conexiones, no pedir el valor en chat. Preguntar qué mecanismo seguro usará el cliente y permitir materializar variables ya presentes en el proceso sin imprimirlas.
- No ejecutar un proyecto con variables obligatorias faltantes o placeholders; registrar `BLOCKED_AUTH` o `BLOCKED_PREFLIGHT`.

Preguntar después por usuarios de prueba y base de datos.

- Preguntar método de autenticación y solicitar solo nombres de variables de entorno.
- Para SQL Server, preferir un usuario de lectura para inspección y otro de escritura limitado a QA para seed y cleanup.
- Si no hay base, buscar aprovisionamiento por API, UI administrativa, fixtures o usuarios existentes.
- Si no existe ninguna vía de aprovisionamiento, generar casos y código, pero marcar las ejecuciones dependientes como `BLOCKED_DATA_SETUP`.

Preguntar si la preparación de datos depende de APIs de terceros. Para cada dependencia, solicitar nombre del servicio, contrato o documentación, disponibilidad de sandbox y autorización para simularlo. No pedir credenciales en chat. Usar un mock contractual solo para validar lógica propia; mantener separada la cobertura contra el proveedor real.

No volver a preguntar variables ya presentes y vigentes en `qa-project.yaml` o en una auditoría de `.env`. Resumir solo nombres y estados; nunca valores.

## Descubrimiento

Con código:

- Analizar rutas, formularios, validaciones y clientes API del frontend.
- Analizar endpoints, contratos, autenticación, modelos, migraciones, fixtures, colas y pruebas del backend.
- Buscar las URLs base de cada ambiente en configuración documentada, CI/CD e infraestructura antes de solicitarlas.
- Preservar commit y rama como evidencia.

Sin código:

- Navegar con el navegador disponible o Playwright.
- Priorizar roles, labels, texto visible y atributos estables.
- Mapear páginas, controles, estados, permisos y recorridos.
- Observar tráfico HTTP sin registrar secretos.
- Evitar compras, emails, pagos, borrados y acciones irreversibles sin autorización.

Con varias fuentes, contrastarlas. Registrar contradicciones y no resolverlas por intuición.

Antes de diseñar casos, leer [comprehensive-coverage.md](references/comprehensive-coverage.md), construir el modelo de negocio y realizar pasadas separadas de inventario, happy path, alternativas, validaciones, estados, roles, datos, integraciones, concurrencia, tiempo y recuperación. En modo black-box, variar una dimensión por vez para inferir causa y efecto; conservar las hipótesis como `inferred` hasta corroborarlas.

Con tableros de tareas:

- Leer [task-boards.md](references/task-boards.md) y limitar la consulta al proyecto y alcance autorizados.
- Extraer jerarquía, user stories, criterios de aceptación, prioridad, estado, sprint o release, etiquetas, dependencias, bugs y referencias a documentación.
- Vincular cada regla y caso generado con el ID estable del work item. Derivar casos negativos y límites aunque la historia solo describa el happy path, marcando la derivación y su confianza.
- Mantener comentarios y adjuntos como referencias sanitizadas; no copiar secretos, PII ni contenido irrelevante al conocimiento QA.

## Diseño y automatización

Usar el perfil `comprehensive` por defecto. Maximizar casos atómicos con valor de cobertura, no el número bruto de archivos. Cubrir cada regla, decisión, estado, transición, rol y riesgo aplicable; evitar duplicados que solo cambien valores dentro de una partición ya cubierta.

Clasificar cada caso con `scenario_family`, `business_rule_ids` y `coverage_dimensions`. Exigir como mínimo `happy-path`, `unhappy-path` y `boundary` por cada combinación aplicable de `feature_id × layer`. Activar las familias adicionales definidas en [comprehensive-coverage.md](references/comprehensive-coverage.md) cuando el dominio presente estados, permisos, cálculos, tiempo, concurrencia, integraciones u otros riesgos.

Crear casos manuales legibles y contratos estructurados. Cada caso debe incluir:

- ID, `feature_id`, capa (`frontend`, `backend` o `e2e`), objetivo, prioridad, riesgo, fuente y `work_item_ids` cuando provenga de un tablero.
- Precondiciones, pasos y resultados esperados.
- Tipo de ejecución: manual, automática o ambas.
- Requisitos de datos, `dataset_id`, setup y cleanup.
- Resultado real, estado de ejecución, evidencia requerida, confianza y trazabilidad.

Entregar los casos en dos representaciones sincronizadas:

- JSON canónico para validación, trazabilidad, automatización e integraciones.
- Formato manual legible en español con bloques `[CASO DE PRUEBA NN]`, pasos numerados, resultado esperado, resultado real y estado. Generarlo con `scripts/render_manual_cases.py`.

Aplicar una compuerta de cobertura por capas:

- Si el producto tiene frontend y backend dentro del alcance, generar obligatoriamente casos separados para ambas capas. No considerar que un caso backend cubre el frontend ni viceversa.
- Para cada flujo funcional, reutilizar el mismo `feature_id` en los casos frontend y backend relacionados y agregar casos `e2e` cuando deba verificarse la integración completa.
- Generar frontend desde UI, rutas, formularios, validaciones visibles, permisos y manejo de errores. Generar backend desde API, servicios, reglas de negocio, autenticación, autorización, persistencia e integraciones.
- Antes de finalizar, ejecutar `scripts/validate_cases.py cases.json --require-layers frontend backend --require-scenarios happy-path unhappy-path boundary --strict` y entregar conteos por capa, familia, regla y feature.
- Si una capa no puede analizarse, no omitirla silenciosamente: registrarla en `coverage.blocked_layers` con estado y evidencia, marcar la entrega como parcial y solicitar la fuente faltante.

Para frontend, usar Playwright con pytest en Python y reutilizar `assets/playwright-python/` cuando corresponda.

Para API:

- Usar pytest + HTTPX + validación de esquema si el proyecto debe ser completamente Python.
- Generar REST Assured solo si el cliente acepta Java. Explicar siempre que REST Assured no es Python.

Para performance:

- Generar Artillery solo si está disponible Node.js.
- Usar Locust cuando el requisito sea runtime completamente Python.
- No ejecutar carga contra producción ni sin límites aprobados.

## Datos y bases

Usar `scripts/generate_dataset.py` para datasets deterministas y `scripts/db_tool.py` para inspección o seed cuando sea aplicable.

Aplicar estas reglas:

- Por cada dataset generado, crear el JSON canónico y exportar también CSV. Para varias tablas o colecciones, crear un CSV por entidad y un `manifest.csv`; no mezclar esquemas distintos en un único archivo.
- Crear siempre un inventario sanitizado JSON, CSV y Markdown con entidad, tabla o colección, cantidad, identificadores y campos visibles. Usar `scripts/data_inventory.py` cuando sea necesario regenerarlo.
- Distinguir `GENERATED_NOT_INSERTED`, `PLANNED_NOT_INSERTED`, `INSERTED` y `CLEANED`. No decir que un dato existe en la base solo porque fue generado o apareció en un dry-run.
- Después de un seed, mostrar el inventario por tabla o colección y guardar un recibo con `db_tool.py --receipt`; enlazar el dataset canónico y los CSV sin exponer datos sensibles.
- Si una entidad depende de una API de terceros, leer [external-service-mocking.md](references/external-service-mocking.md), versionar el contrato y etiquetar el resultado `MOCKED_DEPENDENCY`. No presentar un test con mock como validación de la integración real.
- Al terminar la ejecución, antes del cleanup, usar `scripts/generate_verification_queries.py` con el dataset efectivo. Conservar SQL Server `.sql`, MongoDB `.js`, manifest JSON y resumen Markdown bajo `qa-artifacts/data/verification/<run_id>/`.
- Generar únicamente consultas de lectura filtradas por `qa_run_id` o identificadores exactos del dataset. Excluir campos sensibles y no incluir conexiones. Dejarlas como `GENERATED_NOT_EXECUTED`; ejecutarlas solo si el usuario lo solicita y existen credenciales de lectura.
- Conservar las consultas después del cleanup: sirven para inspección si el cleanup fue diferido de forma autorizada y para comprobar conteo cero si ya se ejecutó. Registrar claramente el estado del cleanup.
- Mantener las claves y relaciones en ambos formatos. Serializar objetos o listas NoSQL como JSON compacto dentro de la celda CSV y representar valores nulos como celdas vacías.
- Ejecutar inspección de metadatos antes de escribir.
- Mostrar dry-run antes de cualquier seed o cleanup.
- Permitir escritura solo en `dev`, `development`, `test`, `qa` o `staging`.
- Exigir `QA_ALLOW_DB_WRITE=true`, `--execute` y `--allow-write`.
- Usar queries parametrizadas, transacciones y rollback ante error.
- Etiquetar registros con `qa_run_id` cuando el esquema lo permita.
- Registrar en el historial un evento por tabla o colección con cantidad, identificadores sanitizados, ambiente, `dataset_id`, `run_id`, `metadata.data_status` y ruta del recibo.
- No ejecutar DDL, `DROP`, `TRUNCATE` ni borrados masivos.
- No usar PII real.

## Preflight, ejecución y defectos

Validar ambiente, conectividad, credenciales, permisos, usuarios, servicios, mocks o sandboxes externos, runtimes y capacidad de setup/cleanup. Usar `scripts/preflight.py` para checks básicos no destructivos. Marcar dependencias faltantes como `BLOCKED_PREFLIGHT`.

Mantener los casos y automatizaciones independientes del ambiente donde fueron diseñados:

- Seleccionar el ambiente de ejecución con `QA_TARGET_ENV`; usar el ambiente configurado en `qa-project.yaml` solo como valor predeterminado.
- Resolver URLs y accesos mediante `QA_<AMBIENTE>_FRONTEND_URL`, `QA_<AMBIENTE>_API_BASE_URL`, `QA_<AMBIENTE>_TEST_USERNAME`, `QA_<AMBIENTE>_TEST_PASSWORD`, `QA_<AMBIENTE>_DB_READ_CONNECTION` y `QA_<AMBIENTE>_DB_WRITE_CONNECTION`.
- Validar las URLs resueltas contra `qa-knowledge/environment-routes.json`. Bloquear el ambiente si falta una ruta requerida o si la variable apunta a otro destino sin aprobación.
- Exigir la auditoría de `.env` de cada proyecto mediante `scripts/env_file_manager.py`. Cargar el archivo sin evaluación de shell y sin sobrescribir variables del proceso.
- Exigir la auditoría stack-aware de `.gitignore` mediante `scripts/gitignore_manager.py`; bloquear publicación si Git ya sigue archivos sensibles.
- Normalizar el nombre del ambiente a mayúsculas y guiones bajos. Ejemplo: `main` usa el prefijo `QA_MAIN_`.
- Exigir que el ambiente esté en `QA_ALLOWED_ENVIRONMENTS`. No reutilizar variables genéricas o de otro ambiente salvo que `QA_ALLOW_GENERIC_ENV_FALLBACK=true`.
- Bloquear `prod` o `production` salvo autorización explícita mediante `QA_ALLOW_PRODUCTION=true`.
- Aplicar el mismo perfil a Playwright, clientes API, Artillery/Locust y setup/cleanup de datos; no mantener selectores de ambiente independientes por herramienta.
- Para escrituras en base, exigir además `QA_ALLOWED_DB_WRITE_ENVIRONMENTS`, `QA_ALLOW_DB_WRITE=true` y las confirmaciones del comando. No habilitar `main` para escritura por defecto.
- Ejecutar preflight nuevamente para cada ambiente y registrar ambiente, URLs sanitizadas, versiones y dataset en el historial.

Para pruebas manuales, preparar datos e instrucciones y permitir que el tester adjunte resultado y evidencia.

Ante una falla:

- Reunir resultado esperado/obtenido, datos, versiones y evidencia sanitizada.
- Buscar duplicados antes de proponer un defecto.
- Mostrar preview antes de escribir en Jira, Xray, Zephyr, TestRail, Azure DevOps u otro sistema.

Registrar flakiness, frecuencia y patrón. Aislar temporalmente solo con visibilidad y acción pendiente.

## Historial y salidas

Registrar cada acción material con `scripts/qa_history.py`. Mantener:

```text
qa-knowledge/
qa-history/
qa-artifacts/
qa-project.yaml
```

No crear todos los artefactos por defecto. Crear únicamente los necesarios para el pedido y enlazarlos desde el historial.

Usar `scripts/dashboard.py` para visualizar SQLite con Streamlit. Mantener el tablero en modo lectura.

## Recursos

| Necesidad | Recurso |
|---|---|
| Preguntas y configuración inicial | [onboarding.md](references/onboarding.md) |
| Tableros, backlog, user stories y criterios de aceptación | [task-boards.md](references/task-boards.md) |
| Código, docs, frontend y tráfico API | [discovery.md](references/discovery.md) |
| `.env`, variables y credenciales | [environment-files.md](references/environment-files.md) |
| Archivos locales y `.gitignore` | [gitignore.md](references/gitignore.md) |
| Casos manuales, contratos y trazabilidad | [test-design.md](references/test-design.md) |
| Exploración, lógica de negocio y máxima cobertura útil | [comprehensive-coverage.md](references/comprehensive-coverage.md) |
| Playwright, API y mantenimiento | [automation.md](references/automation.md) |
| APIs de terceros, sandbox, mocks y fallas simuladas | [external-service-mocking.md](references/external-service-mocking.md) |
| Carga, estrés y NFR | [performance.md](references/performance.md) |
| SQL Server, NoSQL, seed, consultas de verificación y cleanup | [data.md](references/data.md) |
| Preflight, ejecución, defectos y versiones | [execution.md](references/execution.md) |
| Log, métricas y tablero | [audit-dashboard.md](references/audit-dashboard.md) |

## Seguridad

No mostrar, guardar en artefactos ni registrar contraseñas, tokens, cookies, encabezados de autorización o connection strings completas. Los valores pueden permanecer únicamente en el `.env` local protegido, el entorno del proceso o el gestor de secretos autorizado. Sanitizar payloads y evidencias. Trabajar con privilegio mínimo.

Solicitar confirmación antes de:

- Escribir en una base, API o gestor externo.
- Crear defectos o publicar casos.
- Ejecutar carga.
- Realizar acciones con efectos reales o irreversibles.

Si un acceso falla, reportar el recurso, la categoría del error y el siguiente paso seguro. Continuar con las fuentes disponibles.
