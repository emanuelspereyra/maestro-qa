# 030 — Chequeo de versión (avisa, nunca actualiza solo)

## Problema
Quien instaló Maestro QA (pip editable o `uvx` apuntando al repo de GitHub) no tiene
ninguna señal de que salió una versión nueva — hay que acordarse de hacer `git pull`/
`uvx --refresh` a mano. Emanuel pidió explícitamente la versión "avisa nomás" — nunca un
auto-update silencioso, que podría romper algo a mitad de una corrida sin que nadie se
entere.

## Alcance
- `version_check.py`: compara la versión instalada (`importlib.metadata`, funciona
  igual con pip editable, wheel o `uvx`) contra el último release de GitHub (API pública,
  sin auth — el repo ya es público). Si hay una más nueva, devuelve un mensaje con qué
  versión hay y cómo actualizar. Nunca levanta — sin red, repo sin releases todavía, o
  cualquier error de la API, devuelve `None` en silencio (no es una tool crítica).
- Se engancha en `ensure_project()` (la tool de MCP que ya existe para "chequeá mi
  setup") — no una tool nueva, ni algo que corra en cada `run_qa` (sería ruido en cada
  ticket).
- Primer release/tag (`v0.1.0`) para que el mecanismo tenga algo real contra qué
  comparar — hasta ahora el repo nunca tuvo un tag.

**Fuera de esta spec:**
- Auto-update real (aplicar el cambio solo) — descartado explícitamente por Emanuel.
- Notificar por otro canal (email, Slack) — solo aparece cuando alguien corre
  `ensure_project()`, nada proactivo.
- Cachear el chequeo entre corridas — GitHub permite 60 req/hora sin auth, de sobra para
  un equipo chico corriendo esto ocasionalmente. Se agrega si alguna vez es un problema
  real.

## Diseño

### `version_check.py`
```python
def installed_version() -> str:
    return importlib.metadata.version("maestro-qa")

def latest_version() -> str | None:
    # GET https://api.github.com/repos/emanuelspereyra/maestro-qa/releases/latest
    # None si falla la red, si no hay releases (404), o cualquier otro error — nunca levanta

def check_for_update() -> str | None:
    # None si está al día o no se pudo determinar; sino el mensaje para el usuario
```
Comparación de versiones: tuplas de enteros después de separar por `.` y sacar un `v`
inicial si está — alcanza para el esquema simple `MAJOR.MINOR.PATCH` de este proyecto,
no hace falta la librería `packaging` para esto.

### `ensure_project()`
Al final del mensaje que ya devuelve (repos configurados, variables configuradas), si
`check_for_update()` no es `None`, se agrega una línea con el aviso.

## Criterios de aceptación
- Sin releases en GitHub (o sin red): `ensure_project()` funciona exactamente igual que
  antes, sin el aviso — probado mockeando la respuesta de la API.
- Con una versión instalada vieja y un release más nuevo mockeado: el aviso aparece con
  ambas versiones y el comando para actualizar.
- Con la versión instalada ya al día: no aparece ningún aviso.
- Cualquier error de red/API nunca rompe `ensure_project()`.
- Suite completa (`ruff`, `mypy`, `pytest`) en verde.

## Fuera de alcance / backlog
- Auto-update real — descartado.
- Cache del chequeo — no es un problema real todavía.
- Chequeo en otros tools de MCP — solo `ensure_project()` por ahora.
