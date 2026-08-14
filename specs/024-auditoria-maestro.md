# 024 — Auditoría "maestro audit"

## Problema
Pedido explícito de Emanuel: "hagamos un maestro audit para que revise el código, los
casos de prueba, automatización, etc" — una pasada de auditoría amplia sobre todo el
fleet, no un fix puntual. A diferencia de spec 022 (bug hunt dirigido a los 10 agentes
de contenido), acá se cubre también la feature más nueva y riesgosa (spec 023, acceso a
repo real) y la calidad de la propia suite de tests.

## Alcance
5 auditorías paralelas, cada una sobre una dimensión distinta, seguidas de verificación
manual de los hallazgos más severos antes de arreglar nada:
1. Los 10 agentes de contenido (lógica, validación, consistencia prompt↔código).
2. `repo_access.py` + tool-calling de providers (seguridad, robustez ante un LLM que no
   controlamos).
3. `orchestrator.py` + `providers/config.py`/`retry.py` + `mcp_server.py`.
4. Calidad de la suite de tests (huecos de cobertura, asserts débiles).
5. Consistencia specs vs código (drift).

## Diseño

### Hallazgos arreglados

**Crítico — sandbox de `write_file` no excluía `.git/`** (`repo_access.py`). El LLM podía
escribir `.git/hooks/pre-commit` o `.git/config` — reproducido a mano
(`write_file(".git/hooks/pre-commit", "...")` escribía sin error). `commit_changes`
corre 4 subprocesos git en ese mismo working tree inmediatamente después, así que un
ticket con contenido adversarial podía alterar el comportamiento de git ahí, y la
contaminación sobrevive a un refresh (`reset --hard` no toca `.git/` interno). Fix:
`_resolve_safe` rechaza cualquier path dentro de `.git/`.

**Alto — el tope de 8 iteraciones del tool-calling garantizaba perder todo lo hecho.**
Si el modelo seguía pidiendo `tool_use` al llegar al tope, ambos providers devolvían el
texto del último bloque (que no tiene texto, por ser `tool_use`) → `""`. Fix: la última
iteración corta el acceso a `tools`, forzando una respuesta de texto — mismo fix en
`AnthropicProvider` y `OpenAICompatProvider` (implementaciones independientes).

**Alto — `json.loads(fn.arguments)` en `OpenAICompatProvider` sin capturar.** Un modelo
real (sobre todo modelos locales/abiertos) que devuelva argumentos truncados crasheaba
`complete()` entero. Fix: error de decode se reporta como resultado de tool en vez de
propagar.

**Medio-alto — `repo_access.execute()` no capturaba `AttributeError`/`TypeError`.** Un
LLM que mande `args` con forma equivocada (no un dict) rompía sin capturar. Fix:
ampliada la tupla de excepciones capturadas.

**Medio — `automatizacion.py` no caía al flujo sin tools ante una falla real**,
contradiciendo el diseño explícito de spec 023 ("cualquier falla... cae al flujo sin
tools"). Ni el `provider.complete(tools=...)` ni `repo.commit_changes(...)` estaban en un
try/except. Fix: ambos ahora degradan con gracia — una falla en el tool-calling repite la
llamada sin tools; una falla en el commit conserva el código ya generado y lo reporta
como pending_item en vez de perderlo.

**Medio — colisión de nombre de rama** con granularidad de segundo. Fix: microsegundos.

**Medio — `trazabilidad.py` no validaba `id`/`text` de cada `acceptance_criteria`** →
`KeyError` sin mensaje claro. Fix: validado explícitamente.

**Medio — `datos_prueba.py`: `dataset_id: null` explícito no se manejaba** (`.get(key,
default)` solo cubre la clave ausente). Fix: `.get(key) or default`.

**Medio — `automatizacion.py`/`automatizacion_api.py`/`performance.py`: código no-string
del LLM** (ej. una lista de líneas en vez de un string) pasaba la validación de
"truthy" y crasheaba `ast.parse` con `TypeError` sin capturar. Fix: chequeo de tipo
explícito antes de parsear.

**Bajo-medio — `priorizacion_bugs.py` no forzaba el literal fijo de `business_priority`.**
Si el LLM ignoraba la instrucción y devolvía una prioridad real, se imprimía como
legítima. Fix: se fuerza el literal en código en vez de confiar en que el LLM respete la
instrucción (evita también el problema de sensibilidad a mayúsculas para este campo).

**Bajo-medio — `get_provider()` no normalizaba `MAESTRO_PROVIDER`** (case/espacios). Fix:
`.strip().lower()`.

**Bajo — keyword `"carga"` en el routing de `performance` era demasiado genérica**,
matcheaba "pantalla de carga", "carga de archivo", etc. Fix: reemplazada por "prueba de
carga".

**Test frágil** — `test_falls_back_to_blind_generation_without_frontend_repo_configured`
dependía en silencio del cwd real de pytest. Fix: `monkeypatch.chdir` explícito.

**Drift de specs** — spec 001 decía "ningún agente necesita tool-calling" (spec 023 ya lo
implementó); spec 005 decía "escribir a un repo real es CDA-60, todavía en Todo" (spec
023 ya escribe local, solo el push/PR sigue en CDA-60); README no mencionaba spec 023.
Las tres actualizadas.

21 tests nuevos agregados como regresión de cada fix. Suite completa: 193 tests.

## Criterios de aceptación
- Cada bug de esta lista tiene un test que falla sin el fix y pasa con él.
- `write_file` rechaza cualquier path dentro de `.git/`.
- El loop de tool-calling de ambos providers devuelve texto real (no `""`) al llegar al
  tope de iteraciones.
- Una falla en el tool-calling o en el commit de `automatizacion` nunca rompe la corrida
  completa — cae a generación ciega o conserva el código ya generado.
- Suite completa (`ruff`, `mypy`, `pytest`) en verde.

## Fuera de alcance / backlog
- **Concurrencia sobre el mismo cache dir**: dos corridas de `automatizacion` contra el
  mismo repo en paralelo no tienen ningún lock — `git add -A` de una corrida podría
  incluir cambios sin commitear de la otra. No hay evidencia de que Maestro QA procese
  tickets en paralelo hoy — se arregla si aparece un caso real, no preventivamente.
- **`mcp_server.py` no degrada con gracia** si un solo módulo de agente falla al
  importar — el servidor entero no arranca, al contrario del diseño de
  `orchestrator.run()` (que sí tolera agentes faltantes). No arreglado — cambiaría el
  comportamiento de arranque del servidor y no hay evidencia de que haya pasado nunca.
- **Duplicación de fixtures de test** (`FakeProvider` idéntico en 12+ archivos, helper
  `_git()` duplicado entre `test_repo_access.py` y `test_agent_automatizacion.py`) — un
  `conftest.py` compartido lo resolvería, pero es refactor de tests, no un bug. Backlog.
- **Sensibilidad a mayúsculas en otros enums** (severidades de `seguridad`, `regresion`)
  — seguía sin reproducir, ver spec 022. Sigue así.
