# 002 — Orquestador

## Problema
Con el motor core armado (spec 001), falta la pieza que recibe una tarea de testing real
y decide qué agentes especializados corresponden — sin eso, alguien tendría que invocar
cada agente a mano y armar el reporte final él mismo.

## Alcance
Cubre CDA-15/16/17 (epic "Orquestador", CDA-14):
- Intake: aceptar un ticket de Jira o una spec/PRD como texto de entrada.
- Routing: decidir qué agentes especializados corresponde correr para ese input.
- Agregación: juntar los resultados de todos los agentes en un reporte único.

**Fuera de esta spec:** la implementación de los 10 agentes especializados (cada uno tiene
su propia spec, epics CDA-18 a CDA-57) y la integración real con la API de Jira (ver
Backlog). El orquestador define el *contrato* que cualquier agente debe cumplir para
poder registrarse — no depende de que los agentes ya existan.

## Diseño

**Intake** (`orchestrator.py`):
```python
@dataclass
class Intake:
    source: Literal["jira_ticket", "spec"]
    text: str
```
v1 no llama a la API de Jira — recibe el texto ya extraído (pegado o pasado por quien invoca
el servidor MCP). Fetch automático desde Jira queda en backlog.

**Contrato de agente** (`agents/registry.py`):
```python
class Agent(Protocol):
    def run(self, intake: Intake, provider: Provider) -> AgentResult: ...

AGENT_REGISTRY: dict[str, Agent] = {}
```
Cada agente especializado (spec propia, epics CDA-18..57) se registra ahí cuando se
implemente. El orquestador no importa agentes concretos — opera sobre lo que esté
registrado. Esto permite que esta spec y su implementación avancen sin esperar a que los
10 agentes existan.

**Routing** (`classify_agents(intake) -> list[str]`): basado en keywords, no en LLM.
- `casos_manuales` y `trazabilidad` corren siempre — toda tarea necesita casos de prueba y
  su trazabilidad contra el requisito.
- El resto (`automatizacion`, `datos_prueba`, `priorizacion_bugs`, `documentacion`,
  `regresion`, `performance`, `seguridad`) se activan si el texto del intake matchea
  palabras clave asociadas (ej. "seguridad"/"owasp"/"permisos" → agente de seguridad).
- `release_readiness` **no** se rutea por keyword: el orquestador lo corre siempre al final,
  pasándole los resultados de todos los demás agentes que corrieron, como paso de cierre.

**Ejecución y agregación** (`run(intake) -> str`):
- Corre cada agente ruteado que esté presente en `AGENT_REGISTRY` (si un agente todavía no
  se implementó, se omite — no rompe el flujo).
- Si un agente registrado tira una excepción, se captura y se registra como resultado con
  error, sin abortar el resto — un agente roto no debe bloquear el reporte de los demás.
- Corre `release_readiness` al final con los resultados acumulados, si está registrado.
- Agrega todo en un reporte Markdown único: una sección por agente con su output.

## Criterios de aceptación
- Con agentes fake registrados en un test, `classify_agents` rutea según keywords y
  siempre incluye los dos agentes default.
- `run()` con un agente fake que lanza una excepción no interrumpe la ejecución de los
  demás agentes ni la agregación final.
- `run()` con `AGENT_REGISTRY` vacío no explota — devuelve un reporte vacío/informativo en
  vez de un error, porque hoy (antes de implementar los 10 agentes) es el estado real.
- Agregar un agente nuevo al registry no requiere tocar `orchestrator.py`.

## Fuera de alcance / backlog
- ~~**Encadenar agentes de contenido entre sí**~~ — resuelto por [008-encadenar-casos-manuales.md](008-encadenar-casos-manuales.md): `casos_manuales` corre primero y su resultado se inyecta como contexto en los demás agentes de contenido, no solo en `release_readiness`.
- **Fetch real desde la API de Jira** — v1 asume que el texto del ticket ya llega como
  string. Cuando se pida, se resuelve agregando un adaptador de intake nuevo, sin tocar
  `classify_agents` ni la agregación.
- **Routing por LLM en vez de keywords** — ponytail: reglas por keyword son el techo
  conocido de esta versión; si en uso real quedan tickets mal ruteados (ej. "agregar botón
  de exportar CSV" debería activar seguridad pero no tiene ninguna keyword de la lista),
  ahí se justifica upgrade a que el LLM decida el routing. No se construye antes de ver ese
  caso real.
- **Ejecución en paralelo de agentes** — v1 corre secuencial; paralelizar es una
  optimización de latencia, no de correctitud, y se agrega si el tiempo total molesta.
