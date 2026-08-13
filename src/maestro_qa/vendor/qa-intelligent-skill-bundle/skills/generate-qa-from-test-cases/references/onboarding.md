# Onboarding y configuración

## Contenido

- Objetivo
- Secuencia
- Reglas de acceso
- Tableros y user stories
- Configuración
- Configuración existente

## Objetivo

Construir `qa-project.yaml` sin pedir información innecesaria ni secretos. Preguntar de a una. Saltar ramas que no apliquen.

## Secuencia

1. Preguntar nombre del proyecto y ambiente objetivo.
2. Preguntar: “¿Tenés acceso al código fuente?”
3. Si la respuesta es sí:
   - Preguntar monorepo o repositorios separados.
   - Solicitar URL y rama de cada repositorio.
   - Para monorepo, solicitar rutas de frontend y backend.
   - Preguntar si cada repositorio es público o privado, cuál es el proveedor y si el entorno actual ya está autenticado.
   - Si no hay autenticación, ofrecer conectar el proveedor o configurar CLI, SSH, gestor de credenciales o una variable de entorno. Esperar a que el usuario complete o autorice esa conexión.
   - No solicitar el valor de una contraseña, token, clave privada ni URL con credenciales en el chat.
   - Validar en modo no interactivo con `scripts/verify_repository.py --url <URL> --branch <RAMA>` antes de clonar.
   - Considerar el acceso confirmado únicamente cuando la validación devuelve `VERIFIED`.
   - Si falla, informar `not_found`, `authentication`, `authorization`, `network` o `unsupported`.
   - Ante `authentication` o `authorization`, no clonar ni continuar como white-box. Solicitar conexión y repetir la verificación; si el usuario la omite, registrar `BLOCKED_SOURCE_ACCESS`.
   - Después de validar, clonar en una ruta aislada y guardar rama, commit y ruta local.
   - Ofrecer carpeta local o ZIP como alternativa.
4. Si la respuesta es no, activar `black-box`.
5. Preguntar: “¿Tenés documentación funcional o técnica?”
6. Si la respuesta es sí:
   - Solicitar enlaces o archivos.
   - Clasificar PDF, Word, sitio web, wiki, OpenAPI, Postman, ERD o Markdown.
   - Intentar abrir cada fuente.
   - Informar fallas individualmente y continuar.
7. Preguntar: “¿Tenés acceso a un tablero de tareas, backlog o user stories?”
8. Si la respuesta es sí:
   - Leer `references/task-boards.md`.
   - Solicitar proveedor, URL, proyecto o espacio y nombre del tablero.
   - Solicitar el alcance autorizado: sprint, release, épica, filtro, consulta o lista explícita de IDs.
   - Preguntar si el entorno ya está autenticado y el método: conector, CLI, OAuth, gestor de credenciales o variable de entorno.
   - No solicitar el valor de tokens, contraseñas ni cookies. Guardar solamente el método y el nombre de la variable si aplica.
   - Verificar acceso de lectura antes de importar. Marcar `VERIFIED` solo después de una lectura no mutante del proyecto y alcance correctos.
   - Si falla, informar `not_found`, `authentication`, `authorization`, `network` o `unsupported`; registrar `BLOCKED_TASK_BOARD_ACCESS` y continuar con otras fuentes.
   - Preguntar por tipos autorizados: épicas, features, user stories, tareas y bugs; comentarios y adjuntos se incluyen solo si aportan evidencia y están permitidos.
   - Guardar el inventario normalizado en `qa-knowledge/work-items.json` sin secretos ni PII innecesaria.
   - Mantener la escritura deshabilitada por defecto. Publicar o modificar tareas, comentarios o estados solo con preview y autorización explícita.
9. Preguntar qué ambientes podrán ejecutar las automatizaciones, cuál será el predeterminado y guardar solo sus alias. Explicar que `QA_TARGET_ENV` selecciona el perfil y que los valores se cargan desde `QA_<AMBIENTE>_<SETTING>`.
10. Antes de solicitar URLs:
   - Revisar `qa-project.yaml`, `qa-knowledge/environment-routes.json` y todas las fuentes accesibles.
   - Buscar en documentación, OpenAPI, Postman, repositorios, ejemplos de configuración, CI/CD y despliegues.
   - Ejecutar `scripts/discover_environment_routes.py` sobre fuentes locales.
   - Crear o actualizar `qa-knowledge/environment-routes.json` con candidato, fuente y estado.
   - Verificar de forma no destructiva las rutas candidatas.
   - Preguntar de a una solo las rutas faltantes o conflictivas, indicando ambiente y servicio.
   - No inferir una URL de otro ambiente mediante sustitución de texto.
11. Completar por ambiente frontend y API; completar autenticación, administración, OpenAPI y servicios adicionales cuando apliquen. Marcar explícitamente `not-applicable` con motivo.
12. Para cada proyecto local frontend, backend, automatización y performance:
    - Leer `references/gitignore.md`.
    - Ejecutar `scripts/gitignore_manager.py --project <ruta>` en modo preview.
    - Detectar stack, patrones faltantes y archivos sensibles candidatos.
    - Aplicar con `--apply` únicamente el bloque administrado, sin reemplazar reglas existentes.
    - Mantener versionados `qa-project.yaml`, `qa-knowledge/` y examples sanitizados.
    - Si Git ya sigue un archivo sensible, registrar `BLOCKED_TRACKED_SENSITIVE`; no retirarlo del índice ni reescribir historial automáticamente.
13. Para cada proyecto local frontend, backend y automatización:
    - Ejecutar `scripts/env_file_manager.py --project <ruta>` en modo lectura.
    - Buscar `.env`, examples y variables requeridas por el código.
    - Expandir `--qa-setting` para cada ambiente autorizado mediante `--qa-environment`.
    - Informar solo nombres, presencia, placeholders y estado de seguridad.
    - No mostrar valores.
14. Si falta `.env`:
    - Mostrar el example elegido y los nombres que se crearán.
    - Verificar primero el `.gitignore` administrado y crear con `--create`, sin sobrescribir.
    - Usar permisos `0600` y dejar secretos vacíos.
    - Si no hay example, crear el mínimo desde las variables descubiertas.
    - Resolver URLs desde el catálogo antes de preguntar.
    - Preguntar de a una las variables no secretas faltantes.
    - Para secretos, preguntar solamente si se proveerán por gestor, variable de proceso o terminal local.
15. Preguntar por usuarios de prueba, roles y método de autenticación.
16. Preguntar acceso a base o esquema:
   - `read-write`
   - `read-only`
   - `schema-only`
   - `none`
17. Si existe acceso:
    - Solicitar motor, host, puerto, base y ambiente.
    - Preguntar autenticación: usuario/contraseña, Entra, Windows integrada, identidad administrada u otra.
    - Solicitar nombres de variables de entorno, nunca valores.
    - Separar credenciales de lectura y escritura cuando sea posible.
18. Si no existe acceso, preguntar por API de aprovisionamiento, UI administrativa, fixtures y usuarios existentes.
19. Preguntar si la generación o preparación de datos depende de APIs de terceros:
    - Solicitar nombre, contrato o documentación y disponibilidad de sandbox.
    - Preguntar si se autoriza un mock contractual y en qué ambientes.
    - No pedir credenciales; guardar solo nombres de variables por ambiente.
    - Mantener separadas las suites `contract-mock` y `real-sandbox`.
20. Preguntar gestor de casos/defectos y si se permite publicar o solo preparar previews. Reutilizar el proveedor del tablero cuando también gestione casos o defectos, pero mantener separados los permisos de lectura y escritura.
21. Preguntar herramientas aprobadas para API y performance.
22. Mostrar resumen, marcar pendientes y guardar configuración.

## Tableros y user stories

- Tratar el tablero como fuente de aprendizaje y no solo como destino de publicación.
- Preferir acceso de solo lectura para descubrimiento.
- Limitar la consulta al alcance confirmado; no recorrer toda la organización por defecto.
- Guardar IDs, URLs, jerarquía, estado, prioridad, sprint o release y fecha de lectura.
- Tratar criterios de aceptación aprobados como evidencia de requisito. Tratar comentarios, descripciones y cambios de estado como contexto con confianza explícita.
- No interpretar `Done`, `Closed` o equivalentes como prueba funcional aprobada.
- Registrar contradicciones con documentación, código, API o comportamiento observado.

## Reglas de acceso

- No pedir contraseñas ni tokens en chat.
- No aceptar URLs HTTPS que incluyan usuario, contraseña o token.
- No incrustar secretos en YAML, código, logs o screenshots.
- No imprimir ni resumir valores encontrados en `.env`; informar únicamente nombres y estado.
- No sobrescribir `.env`, no versionarlo y no crearlo si Git no lo ignora.
- No sobrescribir `.gitignore`; modificar solo el bloque QA administrado y conservar las reglas del cliente.
- No tratar un archivo sensible ya versionado como resuelto. `.gitignore` no limpia el índice ni el historial.
- Usar autenticación existente del entorno cuando sea posible.
- No asumir que un conector del proveedor comparte credenciales con `git`; verificar cada vía por separado.
- Ejecutar verificaciones Git con prompts interactivos desactivados para no quedar esperando credenciales.
- No instalar dependencias ni ejecutar servicios sin necesidad.
- No mutar repositorios al inspeccionarlos.
- No asumir acceso por recibir una URL; verificarlo.

## Configuración

Guardar solo datos no sensibles y nombres de variables:

`application.frontend_url` y `application.api_base_url` representan únicamente el ambiente predeterminado por compatibilidad. El inventario canónico multiambiente vive en `qa-knowledge/environment-routes.json` y la ejecución usa variables `QA_<AMBIENTE>_*`.

```yaml
project:
  name: "example"
  mode: "hybrid"
  environment: "qa"

repositories:
  layout: "separate"
  frontend:
    url: ""
    branch: "main"
    path: ""
    visibility: "unknown"
    provider: ""
    auth_method: ""
    auth_configured: false
    credential_env: ""
    access_status: "not-checked"
    clone_status: "not-cloned"
    clone_path: ""
    commit: ""
  backend:
    url: ""
    branch: "main"
    path: ""
    visibility: "unknown"
    provider: ""
    auth_method: ""
    auth_configured: false
    credential_env: ""
    access_status: "not-checked"
    clone_status: "not-cloned"
    clone_path: ""
    commit: ""

documentation:
  sources: []

task_boards:
  enabled: false
  provider: ""
  base_url: ""
  project: ""
  board: ""
  scope_type: "current-sprint"
  scope_value: ""
  query: ""
  include_types:
    - "epic"
    - "feature"
    - "user-story"
    - "task"
    - "bug"
  include_comments: true
  include_attachments: true
  auth_method: ""
  auth_configured: false
  credential_env: ""
  access_mode: "read-only"
  access_status: "not-checked"
  knowledge_path: "qa-knowledge/work-items.json"
  write_enabled: false

application:
  frontend_url: ""
  api_base_url: ""
  auth_method: ""
  test_users_available: false

execution:
  default_environment: "qa"
  target_environment_env: "QA_TARGET_ENV"
  allowed_environments:
    - "qa"
  allowed_environments_env: "QA_ALLOWED_ENVIRONMENTS"
  variable_pattern: "QA_{ENV}_{SETTING}"
  route_catalog_path: "qa-knowledge/environment-routes.json"
  required_route_types:
    - "frontend_url"
    - "api_base_url"
  discover_routes_before_prompting: true
  allow_generic_fallback_env: "QA_ALLOW_GENERIC_ENV_FALLBACK"
  allow_production_env: "QA_ALLOW_PRODUCTION"

environment_files:
  audit_enabled: true
  create_if_missing: true
  require_gitignore: true
  permissions: "0600"
  expose_values: false
  projects:
    frontend:
      root: ""
      env_file: ".env"
      template: ""
      status: "not-checked"
    backend:
      root: ""
      env_file: ".env"
      template: ""
      status: "not-checked"
    automation:
      root: ""
      env_file: ".env"
      template: ""
      status: "not-checked"
    performance:
      root: ""
      env_file: ".env"
      template: ""
      status: "not-checked"

gitignore:
  audit_enabled: true
  apply_project_defaults: true
  managed_block: "qa-skill"
  protect_examples: true
  projects:
    frontend:
      root: ""
      status: "not-checked"
    backend:
      root: ""
      status: "not-checked"
    automation:
      root: "qa-automation"
      status: "not-checked"
    performance:
      root: "qa-performance"
      status: "not-checked"

database:
  access_level: "none"
  engine: ""
  host: ""
  port: null
  name: ""
  authentication: ""
  read_connection_env: "QA_{ENV}_DB_READ_CONNECTION"
  write_connection_env: "QA_{ENV}_DB_WRITE_CONNECTION"
  allow_write: false

data_provisioning:
  api_available: false
  admin_ui_available: false
  fixtures_available: false

external_dependencies:
  mocking_allowed: false
  default_mode: "blocked"
  bind_host: "127.0.0.1"
  request_bodies_logged: false
  services: []

data_generation:
  formats:
    - "json"
    - "csv"
  csv_mode: "per-entity"
  csv_encoding: "utf-8"
  create_inventory: true
  require_seed_receipt: true

verification_queries:
  generate_after_execution: true
  execute_automatically: false
  require_filter: true
  include_count_query: true
  include_detail_query: true
  output_dir: "qa-artifacts/data/verification"

test_management:
  provider: ""
  project: ""
  publish_enabled: false

test_generation:
  required_layers:
    - "frontend"
    - "backend"
  include_e2e: true
  require_explicit_blockers: true
  manual_output_format: "spanish-block"

tooling:
  frontend: "playwright-python"
  api: "pytest-httpx"
  performance: "locust"

paths:
  knowledge: "qa-knowledge"
  history: "qa-history"
  artifacts: "qa-artifacts"
```

## Configuración existente

Si el archivo ya existe:

1. Leerlo.
2. Resumir proyecto, modo, ambientes y accesos sin mostrar secretos.
3. Validar enlaces o rutas necesarios para el pedido actual.
4. Preguntar solo por valores faltantes, inválidos o vencidos.
5. No sobrescribir valores confirmados sin informar.
