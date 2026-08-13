# 007 — Agente: datos de prueba

## Problema
Tercer agente del fleet. A diferencia de `casos_manuales` y `automatizacion`, esta pieza no
necesita que el LLM genere el dato final — necesita que el LLM describa **qué entidades y
campos** hacen falta, y que un generador determinista (ya armado en el bundle, spec 003)
produzca los valores. Mezclar ambas cosas en el LLM sería no determinista para algo que
debe ser reproducible por semilla.

## Alcance
Cubre CDA-27/28/29 (epic "Sub-agente: Generación de datos de prueba", CDA-26):
- El LLM genera un `dataset-spec` (entidades, campos, tipos, cantidades) a partir del ticket.
- `scripts/generate_dataset.py` genera el dataset real: JSON canónico + CSV por entidad +
  inventario JSON/CSV/Markdown — determinista por `seed`, sin LLM de por medio.
- Persistir los artefactos en `qa-artifacts/data/<dataset_id>/` (a diferencia de
  `casos_manuales`, que descarta su JSON intermedio — acá el dataset generado *es* el
  entregable, no un paso intermedio).
- Registrarse en `AGENT_REGISTRY["datos_prueba"]`.

**Fuera de esta spec:**
- Seed/cleanup contra una base real (`db_tool.py`) — necesita credenciales y un ambiente QA
  real que no existen en el contexto del agente todavía.
- Mocks de terceros (`mock_api_server.py`, `third-party-mock.template.json`) — levantar un
  servidor no es "generar un archivo", es un artefacto de otra naturaleza. Se ajusta el mapeo
  de spec 003: `mock_api_server.py` queda en backlog explícito, no en el alcance de v1 de
  este agente.

## Diseño

**Por qué el LLM no genera los valores directamente:** los valores del dataset tienen que
ser reproducibles (misma `seed` → mismo dataset, para poder repetir un run o depurar una
falla). Un LLM no es determinista de esa forma. Se le pide en cambio la *forma* de los
datos — igual que `casos_manuales` no le pide al LLM que decida el esquema de un caso de
prueba, se lo damos nosotros y el LLM llena el contenido.

**Prompt:** instruye al LLM con el contrato de `dataset-spec.template.json` (entidades con
`name`, `target`, `identifier_fields`, `display_fields`, `sensitive_fields`, `count`,
`fields`) y los tipos de campo soportados por `generate_dataset.py`: `literal`, `run_id`,
`uuid`, `integer` (min/max), `decimal` (min/max/scale), `boolean`, `choice` (values),
`string` (prefix/length), `username` (prefix), `email` (domain), `date`/`datetime` (base),
`ref` (entity/field). Se le pide devolver solo el `dataset-spec`, no el dataset generado.

**Generación real:** el spec del LLM se escribe a un archivo temporal y se invoca
`generate_dataset.py <spec> --output qa-artifacts/data/<dataset_id>/dataset.json` (que ya
genera CSV e inventario con sus propios defaults, sin necesidad de invocar
`data_inventory.py` aparte — `generate_dataset.py` ya lo hace internamente).

**Validación:** el propio `generate_dataset.py` valida tipos de campo, rangos y referencias
al generar — si el spec del LLM es inválido, el script imprime `ERROR: ...` y sale con
código 1. El agente detecta ese código y levanta una excepción con el mensaje real del
script, sin reimplementar su validación.

**Resultado:** `AgentResult.content` incluye el resumen (`dataset_id`, cantidad de filas por
entidad, estado `GENERATED_NOT_INSERTED`) y las rutas de los artefactos persistidos.

## Criterios de aceptación
- Con un provider fake que devuelve un dataset-spec válido, el agente genera los artefactos
  reales en `qa-artifacts/data/<dataset_id>/` y el `AgentResult` referencia esas rutas.
- Con un provider fake que devuelve un spec con un tipo de campo inválido o un rango
  min>max, el agente lanza una excepción con el mensaje de error real de
  `generate_dataset.py`.
- El estado se reporta siempre como `GENERATED_NOT_INSERTED` — nunca se afirma que el dato
  fue insertado en una base, porque este agente no toca ninguna base real.

## Fuera de alcance / backlog
- **Seed/cleanup real vía `db_tool.py`** — requiere credenciales de ambiente QA y
  autorización explícita (`QA_ALLOW_DB_WRITE=true`, etc.) que no existen en este contexto.
- **Mocks de terceros vía `mock_api_server.py`** — se agrega cuando un caso concreto lo
  necesite; hoy el agente no decide ni levanta mocks.
- **Consultas de verificación post-ejecución** (`generate_verification_queries.py`) — tiene
  sentido después de una ejecución real, no en la generación del dataset.
