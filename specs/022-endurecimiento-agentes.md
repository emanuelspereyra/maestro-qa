# 022 — Endurecimiento: bugs reales encontrados auditando los 10 agentes

## Problema
Pedido explícito de Emanuel: pensar todos los caminos que podrían romper los agentes y
agregar tests. Auditando los 10 agentes + el orquestador + `providers/config.py` aparecieron
4 bugs reales, no solo teóricos.

## Alcance

**1. Extracción de JSON frágil (los 10 agentes).** Cada agente reimplementaba
`_extract_json_object`/`_extract_json_array` con un regex greedy
(`re.search(r"\{.*\}", text, re.DOTALL)`). Con `.*` greedy + `DOTALL`, si la respuesta del
LLM tiene *cualquier* otra `{`/`}` antes o después del JSON real (una nota al final, un
ejemplo inline, `{status}` mencionado en prosa), el regex captura desde la primera hasta la
última llave de todo el texto — mezclando texto no-JSON adentro y rompiendo `json.loads`.
Reproducido con un test. **Fix:** `json_extraction.py` nuevo, usa
`json.JSONDecoder.raw_decode` probando cada candidato de apertura hasta encontrar uno que
parsea como JSON válido — ignora lo que venga después de cerrarse, y prosa/llaves inválidas
antes. Los 10 agentes pasan a importar esto en vez de reimplementarlo.

**2. Tres agentes sin validación estructural de campos requeridos.**
`automatizacion`, `automatizacion_api` y `performance` indexaban `payload["campo"]`
directo sin chequear que el campo exista — si el LLM omite una key, el error es un
`KeyError` críptico en vez de un `ValueError` con mensaje claro (los otros 7 agentes sí
validan antes de usar). `performance` además nunca validaba que `test_type` fuera uno de
los 6 valores válidos. **Fix:** agregar `_validate()` a los 3, mismo patrón que
`documentacion`/`seguridad`/etc.

**3. Routing por keyword ciego a tildes.** `documentacion` (`"documentar"`,
`"documentación"`) y `regresion` (`"regresión"`, `"regression"`) no tenían la variante SIN
tilde en la lista — un ticket escrito rápido sin tildes ("documentacion", "regresion",
comunes en español informal/Jira) no matcheaba ningún keyword de esos agentes.
`performance` tenía el mismo problema con `"estrés"` vs `"estres"`. **Fix:** agregar las
variantes sin tilde explícitas (mismo patrón ya usado, sin normalizar acentos en general —
ver Backlog).

**4. `get_provider()` con `KeyError` críptico.** Sin las 3 variables de entorno
(`MAESTRO_PROVIDER`/`MODEL`/`API_KEY`) configuradas, `os.environ["MAESTRO_PROVIDER"]`
levanta `KeyError: 'MAESTRO_PROVIDER'` sin ninguna pista de qué hacer. **Fix:** chequeo
explícito de las 3, mensaje que apunta a `.env.example`.

## Diseño

**Por qué `json.JSONDecoder.raw_decode` y no un regex más elaborado:** es la herramienta
stdlib exacta para esto — parsear el primer valor JSON válido a partir de una posición dada,
sin necesitar expresiones regulares para algo que ya no es un lenguaje regular (JSON anidado
no es regular). Probar cada candidato de apertura hasta que uno parsee es simple, determinista,
y no depende de heurísticas sobre dónde "debería" terminar el JSON.

**Por qué no normalizar acentos en general (backlog, no fix ahora):** agregar las variantes
sin tilde a mano es la solución más chica que resuelve los casos reales encontrados. Un
normalizador general (`unicodedata.normalize` + strip de diacríticos) es más robusto pero
es una capa nueva para un problema que hoy tiene 3 casos conocidos — se construye si
aparecen más gaps de este tipo, no antes.

## Criterios de aceptación
- Un test reproduce el bug de extracción de JSON con prosa+llaves alrededor del JSON real
  y confirma que ahora se extrae correctamente.
- `automatizacion`/`automatizacion_api`/`performance` levantan `ValueError` con mensaje
  claro ante un campo faltante, no `KeyError`.
- `performance` rechaza un `test_type` fuera de los 6 valores válidos.
- Tickets con "documentacion"/"regresion"/"estres" sin tilde rutean al agente
  correspondiente.
- `get_provider()` sin las 3 variables levanta un `ValueError` con mensaje claro, no
  `KeyError`.
- Toda la suite existente sigue en verde después del refactor de extracción de JSON.

## Fuera de alcance / backlog
- **Normalización general de acentos en el routing** — se agrega si aparecen más gaps
  además de los 3 encontrados acá.
- **Reintento automático del LLM ante JSON inválido** — sigue siendo backlog desde spec 004
  (el orquestador captura el error, no relanza).
- **Sensibilidad a mayúsculas en validaciones de enum** (`performance.test_type`,
  severidades de `seguridad`/`priorizacion_bugs`, `regresion.regression_priority`, etc.):
  hoy comparan exacto contra el valor documentado en el system prompt (ej. `"load"`, no
  `"Load"`). No reproducido con un LLM real todavía — se arregla si aparece un caso
  concreto, no de forma preventiva en los 6+ agentes que tienen enums.
