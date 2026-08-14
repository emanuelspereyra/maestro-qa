# 027 — Integraciones de salida: abstracción de writer + Azure DevOps

## Problema
CDA-58 ("Integraciones de salida") agrupa 4 tickets (Xray, Jira nativo, Trello, ALM) más
Azure DevOps y Linear que surgieron en la conversación — demasiadas variables abiertas
(autenticación, mapeo de datos) para construir todo a la vez sin credenciales reales de
ninguna. Decisión explícita de Emanuel: diseñar una abstracción genérica de "writer"
(mismo patrón que `Provider` para los LLMs) e implementar los backends de a uno. Primero:
**Azure DevOps** (work items) — elegido explícitamente sobre Jira nativo, que era la
opción con menos decisiones pendientes.

## Alcance
- Protocol genérico `Writer` (`src/maestro_qa/writers/base.py`): `WorkItem` de entrada,
  `WriteResult` de salida, un método `create()`. Cualquier backend futuro (Jira, Trello,
  ALM Octane, Linear) implementa este mismo contrato.
- `writers/config.py`: `get_writer()` — opcional a diferencia de `get_provider()` (el
  LLM es obligatorio, el writer no). `None` si `MAESTRO_WRITER` no está seteada.
  `ValueError` claro si está seteada pero faltan las variables del backend elegido, o si
  el valor no es un backend soportado.
- `writers/azure_devops.py`: `AzureDevOpsWriter` — crea un work item por caso de prueba
  vía la REST API de Azure DevOps (`POST .../_apis/wit/workitems/${type}`, JSON Patch,
  auth Basic con PAT). Tipo de work item configurable (`MAESTRO_AZURE_DEVOPS_WORK_ITEM_TYPE`,
  default `Task`) — **no** usa el tipo nativo "Test Case" con su campo `Steps` en XML
  propio de Azure Test Plans (ver Backlog), para no depender de un formato no verificado.
- `casos_manuales.py`: después de generar+validar los casos (sin cambios ahí), si hay un
  writer configurado, publica un work item por caso — título = `title`, descripción en
  HTML con objetivo/precondiciones/pasos/resultado esperado. Reporta qué se publicó y
  qué falló, caso por caso — un caso que falla no frena a los demás, y si el writer ni
  siquiera se pudo configurar (faltan credenciales), el resto del agente sigue
  funcionando igual (mismo criterio de resiliencia que specs 023/024/026).

**Fuera de esta spec:**
- Jira nativo (CDA-72), Xray (CDA-59, descartado — Emanuel confirmó que CDA no usa
  Xray), Trello (CDA-73), ALM Octane (CDA-74, confirmado Micro Focus/HPE, no Azure
  DevOps), Linear como destino — quedan para specs futuras, mismo protocolo `Writer`.
- Work item tipo "Test Case" nativo de Azure Test Plans con su campo `Steps` en XML — sin
  documentación confiable para implementarlo bien sin probar contra una organización
  real. `Task`/`Issue`/lo que sea configurable cubre el caso general.
- Actualizar el estado del work item cuando el caso se ejecuta — este writer solo crea,
  no sincroniza estado después.
- Vincular el work item creado al ticket original (parent/child) — se podría, pero no es
  parte de esta spec, backlog.

## Diseño

### Protocol `Writer`
```python
@dataclass
class WorkItem:
    external_ref: str  # case_id, para trazabilidad en logs/errores
    title: str
    description: str  # HTML, cada backend lo adapta a su formato si hace falta


@dataclass
class WriteResult:
    external_id: str
    url: str


class Writer(Protocol):
    def create(self, item: WorkItem) -> WriteResult: ...


class WriterError(Exception):
    pass
```

### `get_writer()`
```python
MAESTRO_WRITER=azure_devops   # vacío/no seteada = sin writer, comportamiento actual
MAESTRO_AZURE_DEVOPS_ORG=
MAESTRO_AZURE_DEVOPS_PROJECT=
MAESTRO_AZURE_DEVOPS_PAT=
MAESTRO_AZURE_DEVOPS_WORK_ITEM_TYPE=Task   # opcional, default Task
```
Mismo patrón que `providers/config.py`: `.strip().lower()` en el nombre, mensaje de error
que nombra específicamente qué variable falta.

### `casos_manuales.py`
Después de la validación existente (sin tocarla), un paso nuevo que nunca levanta:
publica cada caso, junta URLs creadas y errores por separado, los agrega al `content` del
`AgentResult` en dos secciones (`## Casos publicados`, `## Pendiente`) — nunca cambia el
`artifacts["cases"]` que el resto del pipeline ya consume (spec 008).

## Criterios de aceptación
- Sin `MAESTRO_WRITER` seteada: comportamiento de `casos_manuales` idéntico al actual.
- Con `MAESTRO_WRITER=azure_devops` pero sin `MAESTRO_AZURE_DEVOPS_ORG/PROJECT/PAT`:
  `ValueError` nombrando específicamente qué falta — probado, no solo documentado.
- `AzureDevOpsWriter.create()` arma el request correcto (URL con org/project/tipo, auth
  Basic con PAT, JSON Patch con título/descripción) y parsea `id`/`_links.html.href` de
  la respuesta — probado con la API mockeada (no hay forma de probarla real sin una
  organización de Azure DevOps).
- Un caso que falla al publicar no frena a los demás — se reporta individualmente.
- Si el writer no se puede ni configurar, el resto de `casos_manuales` (validación,
  render, `artifacts["cases"]`) sigue funcionando exactamente igual.
- Suite completa (`ruff`, `mypy`, `pytest`) en verde.

## Fuera de alcance / backlog
- Los otros 4-5 backends (Jira, Xray si cambia de opinión, Trello, ALM Octane, Linear)
  — mismo protocolo `Writer`, un spec por backend cuando se decida el orden.
- Work item tipo "Test Case" nativo con Steps en XML.
- Sincronización de estado / vínculo parent-child con el ticket original.
- Validar contra una organización de Azure DevOps real — sin credenciales en este
  entorno, mismo caveat que SonarQube efímero/GitHub real/providers OpenAI-compat.
