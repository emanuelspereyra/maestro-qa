# 008 — Encadenar casos_manuales con el resto de los agentes

## Problema
Con 3 agentes en pie quedó claro que el hueco anotado en specs 002 y 005 no es teórico:
`datos_prueba` inventaba su propio dataset a partir del ticket crudo, sin ninguna relación
con el `dataset_id`/`requirements` que `casos_manuales` ya había definido en el
`data_contract` de cada caso. Lo mismo le pasa a `automatizacion` con los pasos que
automatiza. El usuario lo pidió explícito: quiere que el fleet funcione encadenado, no como
N interpretaciones independientes del mismo ticket.

## Alcance
- `casos_manuales` corre primero cuando está seleccionado (ya es agente default, así que en
  la práctica es siempre que corre algo).
- Su resultado pasa a estar disponible como contexto adicional para los demás agentes de
  contenido que corran en el mismo `run()` — no solo para `release_readiness`, que ya tenía
  este privilegio.
- `AgentResult` gana un campo `artifacts: dict` para que un agente exponga datos
  estructurados (no solo el string para mostrar) que otro agente pueda consumir sin tener
  que reparsear markdown.

**Fuera de esta spec:** encadenar en la otra dirección (que `casos_manuales` sepa qué generó
`datos_prueba`) — no hay caso de uso todavía. Orquestación con dependencias arbitrarias
entre cualquier par de agentes — sigue siendo "casos_manuales primero, el resto después",
no un grafo general.

## Diseño

**`AgentResult.artifacts`:** dict genérico, vacío por default — no rompe ningún agente ni
test existente que no lo use. `casos_manuales` lo llena con `{"cases": [...]}` (la lista ya
validada, no el texto renderizado).

**Orden de ejecución:** dentro de `run()`, los agentes seleccionados se ordenan para que
`casos_manuales` corra primero. Si su resultado no tiene error, los agentes siguientes (que
no sean `casos_manuales` ni `release_readiness`, que ya se maneja aparte) reciben un
`Intake` enriquecido: el texto original + un bloque `"Casos de prueba ya generados:"` con el
JSON de `artifacts["cases"]`.

**Por qué el texto crudo y no un campo estructurado nuevo en cada agente:** los agentes ya
saben leer texto libre (son prompts de LLM) — agregarles un parámetro estructurado nuevo
significaría cambiar la firma de `Agent.run()` otra vez. Inyectar el contexto en el mismo
`Intake.text` es el cambio más chico que logra el objetivo real: que el LLM de `datos_prueba`
vea los `data_contract` reales al armar su `dataset-spec`, y el de `automatizacion` vea los
`steps` reales al escribir el test.

**Prompts actualizados:** `datos_prueba` y `automatizacion` ahora instruyen: "si el mensaje
incluye casos de prueba ya generados, usá sus `data_contract`/`steps` reales en vez de
inventar los propios". Sigue funcionando standalone (sin ese bloque) exactamente como antes
— es una instrucción condicional, no una dependencia dura.

## Criterios de aceptación
- Con `casos_manuales` y `datos_prueba` corriendo juntos vía el orquestador real, el texto
  que le llega a `datos_prueba` contiene el `dataset_id` que `casos_manuales` puso en su
  `data_contract`.
- Si `casos_manuales` falla (resultado con error), los demás agentes no reciben contexto
  roto — siguen con el intake original sin el bloque de casos.
- Los tests existentes de agentes aislados y del orquestador con `FakeAgent` (sin
  `artifacts`) siguen pasando sin modificarlos.

## Fuera de alcance / backlog
- **Extraer solo los campos relevantes por consumidor** (ej. solo `data_contract` para
  `datos_prueba`, solo `steps` para `automatizacion`) en vez de mandar el JSON completo de
  casos a todos — hoy es más simple mandar todo y que cada prompt filtre lo que le importa;
  se optimiza si el tamaño del contexto se vuelve un problema real.
- **Encadenar `automatizacion` → `datos_prueba`** o cualquier otro par que no involucre a
  `casos_manuales` como primer eslabón — no hay necesidad concreta todavía.
