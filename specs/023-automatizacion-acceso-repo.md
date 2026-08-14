# 023 — Automatización: acceso de lectura y escritura al repo de frontend

## Problema
`automatizacion` (spec 005) genera Page Object + test únicamente a partir del texto del
ticket — nunca vio el código real del frontend. Por eso nunca puede usar un selector
estable de verdad: si el ticket no lo menciona textualmente, el agente lo deja como
`# TODO:` en `pending_items` en vez de inventarlo. Cuando SÍ hay un repo de frontend
configurado y accesible, el agente debería poder explorarlo para encontrar selectores
existentes y, si falta un `data-testid` en un elemento relevante, agregarlo en el código
real con una convención estable (`id-testautomation-*`) — no solo señalarlo como pendiente.

## Alcance
- El agente verifica si hay un repo de frontend configurado y accesible (reusa
  `repositories.frontend` de `qa-project.yaml` + `onboarding._verify_repo`, spec 009). Si
  no hay repo configurado, o la verificación falla, el agente funciona EXACTAMENTE como
  hoy (spec 005) — cero cambio de comportamiento en ese caso.
- Si hay repo verificado: clona (shallow) a un directorio de cache local
  (`~/.cache/maestro-qa/repos/<slug>/`, reusable entre corridas), y le da al LLM 3
  herramientas para explorar y modificar ese clone: `list_files`, `read_file`,
  `write_file` — todas confinadas al root del clone (rechaza cualquier path que escape,
  incluyendo `..` y absolutos fuera del root).
- Si durante la exploración el LLM usa `write_file` (por ejemplo, para agregar
  `data-testid="id-testautomation-<algo>"` a un componente existente que no tenía
  selector estable), el agente crea una rama nueva (`automatizacion/<slug>-<timestamp>`)
  y hace commit local de los archivos tocados — **nunca push, nunca PR**. La rama queda
  en el clone local para que un humano la revise y la suba a mano.
- Esto requiere que `Provider.complete()` soporte tool-calling (loop de exploración) —
  se agrega como capacidad genérica de la abstracción de providers, no como algo
  específico de `automatizacion`, para que cualquier agente futuro la pueda reusar.

**Fuera de esta spec:**
- Push/PR automático — es CDA-60 ("Writer hacia repo de código"), decisión explícita de
  Emanuel de frenar en "commit local, sin push" por ahora.
- Backend/API — mismo patrón podría aplicar a `automatizacion_api`, pero no se pidió acá.
  Si se quiere después, es extender el mismo `repo_access.py`, no reinventar.
- Búsqueda por grep/keywords en vez de exploración por LLM — evaluada y descartada por
  decisión explícita: "el LLM explora el repo".
- Verificar que el tool-calling funcione igual en los 7 providers reales (Anthropic +
  OpenAI/Gemini/Kimi/Qwen/DeepSeek vía el adapter OpenAI-compat) — implementado contra el
  formato estándar de cada SDK, pero sin probar contra las 5 APIs OpenAI-compat reales
  (no hay API keys en este entorno). Mismo caveat que SonarQube efímero (spec 015): probar
  a mano con `scripts/smoke_test.py` extendido antes de confiar en producción con un
  provider no-Anthropic.

## Diseño

### Detección de acceso a repo
`repo_access.get_frontend_repo(qa_project_path)` lee `qa-project.yaml`, y si
`repositories.frontend.url` está seteada, reusa `onboarding._verify_repo` (ya existe,
spec 009) para confirmar que es accesible de solo lectura. Si no hay URL o la
verificación no es `VERIFIED`, devuelve `None` — `automatizacion.py` interpreta `None`
como "sin acceso, generar a ciegas como siempre".

### Clone y cache
Si verificado, `git clone --depth 1 --branch <branch> <url> <cache_dir>` — si el path de
cache ya existe (corrida anterior), hace `git fetch` + `reset --hard` en vez de re-clonar.
Nunca toca el working directory del usuario ni un checkout que no sea el propio cache de
Maestro QA.

### Herramientas expuestas al LLM (sandboxed al root del clone)
```
list_files(path: str = ".") -> lista de archivos/carpetas bajo path
read_file(path: str) -> contenido del archivo
write_file(path: str, content: str) -> escribe/sobreescribe el archivo, devuelve "ok"
```
Cada una resuelve `path` con `Path(root, path).resolve()` y rechaza si el resultado no es
relativo a `root.resolve()` — mismo tipo de chequeo que cualquier sandbox de filesystem,
evita que el LLM escape el clone (`../../etc/passwd`, paths absolutos, symlinks fuera).

### Tool-calling en `Provider`
`Provider.complete()` gana dos parámetros opcionales, con default `None` (sin ellos, cero
cambio de comportamiento en los 9 agentes que no los usan):
```python
def complete(
    self, system: str, messages: list[dict], *,
    tools: list[dict] | None = None,
    tool_executor: Callable[[str, dict], str] | None = None,
    **kwargs,
) -> str: ...
```
Con `tools` seteado, cada provider corre un loop interno: llama al LLM, si la respuesta
pide una tool call, ejecuta `tool_executor(name, args)`, agrega el resultado a los
mensajes, y vuelve a llamar — hasta que el LLM devuelve texto final sin tool calls.
Tope de 8 iteraciones (`# ponytail: si un caso real necesita más, subir el número o
loguear cuántas iteraciones hizo falta — no hay señal hoy de que 8 no alcance`); si se
llega al tope, se devuelve el último texto/error del LLM en vez de colgarse.

`AnthropicProvider`: usa bloques `tool_use`/`tool_result` nativos del SDK.
`OpenAICompatProvider`: usa `tools=[{"type": "function", ...}]` + `tool_calls` del
formato estándar OpenAI — mismo adapter que ya cubre OpenAI/Gemini/Kimi/Qwen/DeepSeek.

### Flujo de `automatizacion.py`
1. `repo = repo_access.get_frontend_repo(qa_project_path)` — `None` si no hay acceso.
2. Si `repo is None`: exactamente el flujo de spec 005 (sin tools).
3. Si hay `repo`: arma las 3 tools sobre `repo.path`, llama a `provider.complete(...,
   tools=tools, tool_executor=repo.execute)`, con el mismo prompt de siempre más una
   instrucción extra: "tenés acceso al código real del repo de frontend vía `list_files`/
   `read_file`/`write_file` — explorá antes de escribir el test, y si un elemento
   relevante no tiene selector estable, agregale `data-testid=\"id-testautomation-
   <slug>\"` con `write_file` en vez de dejarlo como pendiente."
4. Si `repo.touched_files` no está vacío al terminar el loop: crea rama
   `automatizacion/<feature-slug>-<timestamp>`, `git add -A && git commit`. El resultado
   del agente incluye una sección `## Cambios en el repo de frontend` con la rama, el
   path local, y la lista de archivos tocados — para que Emanuel la revise y la suba a
   mano.
5. Cualquier falla en 1-4 (clone falla, git error, tool loop tira excepción) cae al
   flujo de spec 005 sin tools — nunca rompe la corrida completa del agente por un
   problema de acceso a repo. Se agrega una nota a `pending_items`: "no se pudo usar el
   repo de frontend (<motivo>), automatización generada sin ese contexto."

## Criterios de aceptación
- Sin `repositories.frontend` configurado en `qa-project.yaml` (o sin verificar), el
  comportamiento de `automatizacion` es idéntico al de spec 005 — ningún test existente
  de `test_agent_automatizacion.py` cambia.
- Con un repo local de prueba (creado con `git init` en un test, sin red) y un
  `FakeProvider` que simula un loop de tool-calls (`list_files` → `read_file` →
  `write_file` → texto final), el resultado incluye la rama creada, y el archivo
  modificado existe con el commit en esa rama del clone.
- `list_files`/`read_file`/`write_file` rechazan cualquier path que intente escapar el
  root del clone.
- El tope de iteraciones del loop de tool-calling se respeta — un `FakeProvider` que
  simula tool-calls infinitos no cuelga el test.
- Ningún push ni operación de red de escritura ocurre en ningún test ni en el código.
- Suite completa (`ruff`, `mypy`, `pytest`) sigue en verde.

## Fuera de alcance / backlog
- Push/PR automático (CDA-60) — decisión explícita de Emanuel de no hacerlo todavía.
- Aplicar el mismo patrón a `automatizacion_api` contra un repo de backend.
- Validar tool-calling contra las 5 APIs OpenAI-compat reales (Gemini/Kimi/Qwen/DeepSeek)
  — sin API keys en este entorno, queda para probar a mano como con SonarQube efímero.
- Reusar el clone entre agentes de una misma corrida (hoy cada llamada a
  `get_frontend_repo` re-verifica/re-clona; si esto se vuelve lento, cachear por
  proceso).
