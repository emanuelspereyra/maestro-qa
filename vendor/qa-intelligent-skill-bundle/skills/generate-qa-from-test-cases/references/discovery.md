# Descubrimiento del producto

## Contenido

- Selección del modo
- Inventario de evidencia
- Rutas por ambiente
- White-box
- Black-box
- Modelado de lógica de negocio
- Exploración por pasadas
- Tableros y user stories
- Documentación
- Reconciliación
- Artefactos

## Selección del modo

Usar `white-box` con repositorios, `black-box` con aplicación desplegada y `hybrid` cuando haya ambas fuentes. Preferir híbrido sin exigirlo.

## Inventario de evidencia

Registrar por fuente:

- Tipo y ubicación.
- Fecha de lectura.
- Rama, commit o versión.
- Alcance analizado.
- Estado de acceso.
- Reglas y entidades extraídas.
- Confianza: `confirmed`, `inferred` o `pending`.

No almacenar credenciales, payloads sensibles ni respuestas completas con PII.

## Rutas por ambiente

Antes de preguntarle una URL al usuario, buscarla en este orden:

1. `qa-project.yaml` y `qa-knowledge/environment-routes.json`.
2. Manuales, runbooks, wikis, OpenAPI `servers` y ambientes de Postman.
3. README y configuración pública de ejemplo de frontend y backend.
4. Workflows CI/CD, variables no secretas, manifiestos Kubernetes, Helm, Terraform y archivos de despliegue.
5. Configuración runtime visible y tráfico del frontend autorizado.

En fuentes locales, ejecutar:

```bash
python scripts/discover_environment_routes.py \
  --root docs \
  --root frontend \
  --root backend \
  --environment dev,main,qa,staging \
  --output qa-knowledge/environment-routes.json
```

El script omite `.env` reales y directorios de dependencias. Sus resultados son candidatos: revisar contexto, conflictos y falsos positivos antes de marcarlos como documentados o verificados.

Inventariar por ambiente:

- `frontend_url`
- `api_base_url`
- `auth_url`, si existe un proveedor o issuer separado.
- `admin_url`, si se usa para preparar datos.
- `openapi_url`, si el contrato está desplegado.
- Bases de GraphQL, WebSocket, archivos, pagos simulados u otros servicios dentro del alcance.

Las rutas funcionales como `/login`, `/users` o `/items/{id}` se catalogan una vez en `site-map.json` o `api-catalog.json` y se resuelven sobre la URL base del ambiente. No pedir la misma ruta funcional para cada ambiente.

Estados permitidos:

- `candidate`: hallada pero todavía no revisada.
- `documented`: respaldada por una fuente identificada.
- `verified`: accesibilidad comprobada sin mutaciones.
- `conflict`: existen valores incompatibles.
- `missing`: no se encontró.
- `not-applicable`: el servicio no existe en ese ambiente, con motivo.
- `access-blocked`: la fuente o ruta requiere acceso faltante.

Si una ruta requerida queda `missing`, `conflict` o `access-blocked`, preguntar de a una con este formato:

```text
No encontré una URL confirmada para la API del ambiente main.
¿Cuál es la URL base o dónde está documentada?
```

No preguntar rutas ya documentadas y vigentes. No construir URLs de otros ambientes reemplazando palabras, subdominios o sufijos. Sanitizar usuario, contraseña, query y fragmento antes de guardar una URL.

## White-box

### Frontend

Identificar:

- Rutas y navegación.
- Páginas, componentes, formularios y tablas.
- Campos requeridos, máscaras y validaciones.
- Roles, feature flags y permisos visibles.
- Clientes HTTP, endpoints y manejo de errores.
- Selectores accesibles y test IDs.
- Estado global, caché y almacenamiento local.
- Pruebas existentes y configuración CI.
- Condiciones de render, guards, estados, feature flags y ramas de error.

### Backend

Identificar:

- Endpoints, controladores, servicios y contratos.
- Autenticación, autorización y roles.
- Reglas de negocio y validaciones.
- Modelos, migraciones, relaciones e índices.
- Seeds, fixtures y factories.
- Jobs, colas, eventos y tareas programadas.
- Integraciones externas y feature flags.
- Pruebas existentes, cobertura y CI.
- Máquinas de estado, tablas de decisión, cálculos, transacciones, retries e idempotencia.

No modificar archivos durante el descubrimiento. Conservar commit y rama en el modelo de conocimiento.

Cuando existan frontend y backend, no cerrar el descubrimiento después de analizar una sola capa. Crear inventarios separados y relacionarlos por flujo:

```text
flujo visible -> ruta/componente frontend -> request -> endpoint/servicio backend -> entidad o efecto
```

Si una capa queda sin analizar, registrar `BLOCKED_SOURCE_ACCESS`, `BLOCKED_PREFLIGHT` o `NOT_APPLICABLE` con evidencia. No pasar silenciosamente al diseño como si la cobertura fuera completa.

## Black-box

### Navegación

1. Confirmar ambiente y cuenta autorizada.
2. Iniciar con páginas públicas y acciones de lectura.
3. Mapear menús, rutas, tabs, modales, formularios y estados.
4. Priorizar `get_by_role`, `get_by_label`, `get_by_placeholder` y `get_by_test_id`.
5. Observar mensajes, validaciones, estados vacíos, errores y permisos.
6. Capturar evidencia mínima necesaria.
7. No confirmar acciones con efecto real sin autorización.
8. Repetir el flujo con roles, estados y particiones de datos distintos.
9. Variar una dimensión por vez y registrar causa, efecto y confianza.
10. Revisar refresh, back/forward, doble envío, expiración y recuperación.

### Tráfico API

Observar:

- Método y ruta normalizada.
- Código de estado.
- Content-Type.
- Nombres de campos de request/response.
- Parámetros y paginación.
- Relación entre acción UI y endpoint.
- Requisitos aparentes de autenticación.

Sanitizar Authorization, Cookie, Set-Cookie, tokens, emails, teléfonos, identificadores personales y cuerpos sensibles.

No realizar fuzzing, enumeración agresiva ni replay de operaciones destructivas sin permiso explícito.

## Modelado de lógica de negocio

Leer [comprehensive-coverage.md](comprehensive-coverage.md) y construir antes de los casos:

- Actores, roles, ownership y tenants.
- Entidades, relaciones, restricciones y ciclos de vida.
- Estados, transiciones, guardas y acciones prohibidas.
- Reglas, decisiones, invariantes, cálculos y restricciones temporales.
- Integraciones, eventos, efectos secundarios y modos de falla.

Asignar IDs `BR-<dominio>-NNN`, fuente y confianza. Con código, extraer ramas relevantes sin declarar que la implementación es correcta. Sin código, inferir candidatos desde controles condicionales, mensajes, diferencias de roles, secuencias UI/API y cambios de estado; mantenerlos `inferred` hasta corroborarlos.

## Exploración por pasadas

No cerrar el mapa después del happy path. Realizar pasadas separadas de inventario, alternativas, validaciones, estados, roles, datos, integraciones, concurrencia, tiempo, recuperación y no funcionales aplicables.

Después de cada pasada, actualizar `business-model.json`, `business-rules.json`, `scenario-inventory.json` y la matriz de cobertura. Detener la expansión solo cuando las nuevas pasadas produzcan duplicados dentro de particiones ya cubiertas y todo riesgo residual quede documentado.

## Documentación

Leer manuales, requisitos, OpenAPI, Postman, wikis y diagramas. Si una fuente no abre:

1. Registrar `ACCESS_BLOCKED`.
2. Indicar el motivo verificable.
3. Solicitar exportación, adjunto o acceso.
4. Continuar sin inventar su contenido.

## Tableros y user stories

Leer `references/task-boards.md` cuando exista Jira, Azure DevOps Boards, Linear, GitHub Issues/Projects u otro tablero autorizado.

1. Verificar acceso de lectura y el proyecto correcto.
2. Limitar la consulta al sprint, release, épica, filtro, query o IDs autorizados.
3. Normalizar work items en `qa-knowledge/work-items.json`.
4. Extraer jerarquía, criterios de aceptación, prioridad, estado, etiquetas, dependencias, bugs y referencias documentales.
5. Relacionar el ID del work item con reglas, `feature_id`, casos y defectos.
6. Registrar fecha de lectura, URL y versión o fecha de actualización para detectar cambios.

No tratar el estado `Done` como evidencia de prueba aprobada. Los comentarios aportan contexto, pero requieren confianza explícita y no reemplazan criterios de aceptación aprobados. No copiar secretos, PII ni adjuntos completos al conocimiento QA.

## Reconciliación

Cuando las fuentes se contradigan:

1. Registrar ambas versiones.
2. Preferir requisitos aprobados para el oracle.
3. Usar el código para entender la implementación, no para declarar que es correcta.
4. Usar el comportamiento real como evidencia, no como especificación automática.
5. Marcar la regla `pending` y solicitar decisión si afecta una aserción.

## Artefactos

Actualizar según necesidad:

```text
qa-knowledge/
├── sources.json
├── work-items.json
├── environment-routes.json
├── site-map.json
├── api-catalog.json
├── entities.json
├── business-model.json
├── business-rules.json
├── decision-tables.json
├── scenario-inventory.json
├── coverage-matrix.json
├── observations.json
├── contradictions.json
├── frontend-inventory.json
├── backend-inventory.json
└── flow-layer-map.json
```
