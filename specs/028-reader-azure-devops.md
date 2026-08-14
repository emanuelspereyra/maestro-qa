# 028 — Reader de Azure DevOps (traer work items reales)

## Problema
Hasta ahora `run_qa(source, text)` solo recibe texto pegado a mano — no hay forma de que
Maestro QA traiga un ticket real desde ningún sistema. Emanuel confirmó que CDA ya usa
Azure DevOps de verdad para un par de proyectos (motivo por el que spec 027 empezó por ahí
como *destino* de escritura) — ahora hace falta también el sentido contrario: leer un work
item real de Azure DevOps y usarlo como intake, sin copiar/pegar texto a mano.

## Alcance
- Protocol genérico `Reader` (mismo patrón que `Writer` de spec 027): `fetch(external_id)`
  devuelve un `FetchedTicket` (título + texto ya armado, listo como `intake.text`).
- `AzureDevOpsReader`: trae un work item por ID vía la REST API de Azure DevOps (mismas
  credenciales que el writer — `MAESTRO_AZURE_DEVOPS_ORG/PROJECT/PAT`, un flag separado
  `MAESTRO_READER=azure_devops` para habilitar la lectura independientemente de si el
  writer está activo).
- Nuevo tool de MCP `run_qa_from_work_item(work_item_id)`: trae el work item y corre el
  pipeline completo en un solo paso — no hace falta un tool separado de "solo traer texto"
  para el caso de uso principal (correr Maestro QA sobre un ticket real).
- Descripción HTML del work item se limpia a texto plano antes de mandarla al LLM (misma
  razón que cualquier prompt: menos ruido, no HTML crudo).

**Fuera de esta spec:**
- Readers para otros sistemas (Jira, Trello) — mismo protocolo, se agregan cuando se
  prioricen (igual que los writers de spec 027).
- Sincronizar de vuelta el resultado al mismo work item que se leyó (ej. comentario con
  el veredicto de `release_readiness`) — separado, backlog.
- Búsqueda/listado de work items (por query, por sprint) — esta spec es "traer UNO por
  ID", no un explorador.

## Diseño

### `Reader` protocol
```python
@dataclass
class FetchedTicket:
    external_id: str
    title: str
    text: str  # armado y listo como intake.text


class Reader(Protocol):
    def fetch(self, external_id: str) -> FetchedTicket: ...


class ReaderError(Exception):
    pass
```

### `AzureDevOpsReader`
`GET https://dev.azure.com/{org}/{project}/_apis/wit/workitems/{id}?api-version=7.1`,
auth Basic con el mismo PAT que el writer. Extrae `System.Title` y
`System.Description` (o `Microsoft.VSTS.TCM.ReproSteps` si la descripción está vacía —
común en work items tipo Bug), le saca las etiquetas HTML, arma
`f"{title}\n\n{description}"` como `text`.

### `get_reader()`
Mismo patrón que `get_writer()`: `None` si `MAESTRO_READER` no está seteada (opcional),
`ValueError` claro si está seteada pero faltan credenciales, reusa las mismas
`MAESTRO_AZURE_DEVOPS_*` que ya usa el writer (mismo org/project, no se duplican).

### `mcp_server.py`
```python
@mcp.tool()
def run_qa_from_work_item(work_item_id: str) -> str:
    """Trae un work item real de Azure DevOps por ID y corre Maestro QA sobre su
    contenido — necesita MAESTRO_READER=azure_devops configurado."""
```
Sin reader configurado, o si falla la lectura (404, PAT inválido), devuelve un mensaje
claro en vez de una excepción cruda — mismo criterio que el resto del proyecto.

## Criterios de aceptación
- Sin `MAESTRO_READER` seteada: el tool nuevo devuelve un mensaje claro, no una excepción.
- `AzureDevOpsReader.fetch()` arma el request correcto y parsea título/descripción,
  incluyendo el fallback a `ReproSteps` — probado con la API mockeada.
- HTML de la descripción se limpia a texto plano antes de usarse.
- `run_qa_from_work_item` corre el pipeline completo (agentes reales, no solo el fetch)
  cuando el reader está configurado — probado end-to-end con un provider fake.
- Suite completa (`ruff`, `mypy`, `pytest`) en verde.

## Fuera de alcance / backlog
- Readers para Jira/Trello — mismo protocolo, backlog.
- Sincronizar el resultado de vuelta al work item origen.
- Búsqueda/listado de work items por query — solo fetch por ID en esta spec.
- Validar contra una organización de Azure DevOps real — mismo caveat que el writer
  (spec 027), sin credenciales en este entorno.
