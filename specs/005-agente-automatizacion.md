# 005 — Agente: automatización (Page Object Model)

## Problema
Segundo agente del fleet — genera automatización frontend en Playwright Python siguiendo
Page Object Model, para los casos que lo justifican. Es la pieza que más se apoya en
`vendor/qa-intelligent-skill-bundle` (spec 003): `references/automation.md` ya define las
reglas (qué evitar, cómo resolver ambiente, estructura de carpetas) y
`assets/playwright-python/` ya trae el scaffold (`conftest.py`, `qa_environment.py`,
`base_page.py`).

## Alcance
Cubre CDA-23/24/25 (epic "Sub-agente: Automatización (Page Object Model)", CDA-22):
- Generar un Page Object (subclase de `BasePage`) + un test pytest+Playwright a partir del
  texto del ticket.
- Validar que el código generado sea Python sintácticamente válido antes de devolverlo.
- Registrarse en `AGENT_REGISTRY["automatizacion"]`.

**Fuera de esta spec:**
- Automatización de backend/API (pytest+HTTPX) — `automation.md` la cubre, pero el epic de
  Linear la nombra explícitamente "Page Object Model", que es un patrón de UI. Si CDA pide
  automatización de API, es un agente nuevo, no una extensión de este.
- Copiar `assets/playwright-python/` a un repo de cliente nuevo — es un paso de bootstrap
  del proyecto, no algo que este agente haga por ticket.
- Escribir el código generado en un repo real (PR) — eso es CDA-60 ("Writer hacia repo de
  código"), todavía en Todo.
- Ejecutar el test generado contra un browser real — sin sandbox de ejecución, este agente
  no corre Playwright, solo lo genera (ver Backlog).

## Diseño

**Por qué no depende de la salida de `casos_manuales`:** en el diseño actual del
orquestador (spec 002), cada agente recibe el mismo `Intake` de forma independiente — no
hay paso de resultados entre agentes salvo hacia `release_readiness`. Encadenar
`automatizacion` a los casos JSON de `casos_manuales` sería más preciso, pero requiere
cambiar el orquestador para pasar resultados intermedios entre agentes "de contenido", no
solo hacia el agente final. Se documenta como mejora en Backlog — v1 genera la
automatización directamente del texto del ticket, con su propio prompt.

**Prompt:** instruye al LLM con las reglas de `automation.md` (locators por rol/label/
testid, web-first assertions, sin `time.sleep`, sin selectores XPath/CSS frágiles, resolver
`base_url` vía fixture en vez de hardcodear, Page Object solo si reduce duplicación real) y
le pide devolver JSON con:
```json
{
  "page_object_filename": "pages/<feature>_page.py",
  "page_object_code": "...",
  "test_filename": "tests/test_<feature>.py",
  "test_code": "...",
  "pending_items": ["..."]
}
```
`pending_items` es obligatorio (puede ser lista vacía) — ahí van URLs, selectores o datos
que el LLM no pudo determinar del ticket. Mirror de la regla de `automation.md`: "si faltan
URL, autenticación, selector, contrato o dato, marcar el punto como pendiente y no
inventarlo."

**Validación:** `ast.parse()` sobre ambos bloques de código antes de devolver el resultado.
No ejecuta el test (no hay sandbox de browser en este agente) — solo garantiza que lo que se
entrega es Python válido, no pseudocódigo roto. Si algún bloque no parsea, se levanta una
excepción (el orquestador la captura, spec 002).

**Resultado:** `AgentResult.content` incluye ambos archivos generados (con su ruta sugerida)
y, si hay `pending_items`, los lista de forma visible — no los oculta en el JSON.

## Criterios de aceptación
- Con un provider fake que devuelve Page Object + test válidos, el agente devuelve un
  `AgentResult` con ambos bloques de código y sin excepción.
- Con un provider fake que devuelve código con un error de sintaxis, el agente lanza una
  excepción indicando cuál de los dos archivos falló.
- Si el LLM reporta `pending_items`, aparecen en el `content` del resultado, no se pierden.

## Fuera de alcance / backlog
- ~~**Encadenar con los casos de `casos_manuales`**~~ — resuelto por
  [008-encadenar-casos-manuales.md](008-encadenar-casos-manuales.md): el prompt ahora
  automatiza los `steps` reales cuando el orquestador inyecta los casos ya generados.
- **Ejecutar el test generado** — necesita un browser real, credenciales de ambiente QA y
  la app corriendo; ninguna de esas piezas existe todavía en el proyecto.
- **Automatización de API (backend)** — agente nuevo si CDA lo pide, no parte de este.
