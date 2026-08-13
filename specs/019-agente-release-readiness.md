# 019 — Agente: release readiness (décimo y último del plan original)

## Problema
Cierra el plan original de 10 agentes. El orquestador (spec 002) ya tiene la lógica
especial esperando este nombre — corre al final, con un intake distinto al resto: no el
ticket, sino el resumen de lo que hicieron todos los demás agentes en el mismo run. Falta
la pieza que lee ese resumen y da un veredicto.

## Alcance
Cubre CDA-55/56/57 (epic "Sub-agente: Reporte de release-readiness", CDA-54):
- El LLM lee el resumen agregado (todos los agentes que corrieron + su contenido) y da un
  veredicto: `GO`, `GO_WITH_CONDITIONS` o `NO_GO`, con motivo.
- El orquestador, no el LLM, detecta de forma determinística si algún agente falló en este
  run y se lo dice explícito en el intake (no depende de que el LLM note un error
  mencionado en medio de texto libre).
- Si el orquestador detectó errores mientras el LLM dijo `GO`, el agente corrige el
  veredicto a `NO_GO` él mismo — no relanza al LLM, no confía en que lo note solo.
- Registrarse en `AGENT_REGISTRY["release_readiness"]`.

**Fuera de esta spec:**
- El dashboard visual (`dashboard.py`, Streamlit) — es para ver el historial de *muchos*
  runs, este agente da un veredicto de *un* run. Se conectan si hace falta verlo
  visualmente, no antes.
- Publicar el veredicto en algún lado — mismo patrón que el resto, depende de writers que
  no existen.

## Diseño

**Cambio chico al orquestador:** `run()` ahora arma el intake de `release_readiness` con un
encabezado determinístico —
`"Agentes con error: <lista o 'ninguno'>"` — antes del resumen agente-por-agente (que
también marca `(ERROR)` en la línea de cada agente que falló). Antes el intake no
distinguía error de éxito en el texto; ahora sí, de forma que el propio agente pueda
verificarlo sin depender del LLM.

**Prompt:** pide leer el resumen y decidir `GO`/`GO_WITH_CONDITIONS`/`NO_GO` con
`blocking_issues` (lo que impide un GO limpio) y `non_blocking_notes` (observaciones que no
bloquean). No inventa detalles que no estén en el resumen — si el resumen es escueto, lo
dice en vez de rellenar.

**Formato de salida:**
```json
{
  "overall_status": "GO|GO_WITH_CONDITIONS|NO_GO",
  "summary": "...",
  "blocking_issues": ["puede estar vacía"],
  "non_blocking_notes": ["puede estar vacía"]
}
```

**Corrección determinística:** el agente parsea el encabezado `"Agentes con error: ..."`
del propio intake (formato que el orquestador controla, no el LLM) — si hay al menos un
agente con error y el LLM devolvió `GO`, se fuerza a `NO_GO` y se agrega una nota explícita
("Corregido a NO_GO: N agente(s) fallaron en este run") en vez de confiar en que el LLM lo
haya visto solo.

## Criterios de aceptación
- Con un resumen sin errores y el LLM devolviendo `GO`, el resultado queda `GO` sin
  modificar.
- Con al menos un agente marcado `(ERROR)` en el resumen y el LLM devolviendo `GO` de
  todos modos, el agente lo corrige a `NO_GO` con la nota explicando por qué.
- `overall_status` fuera de los 3 valores válidos levanta una excepción.
- El orquestador sigue agregando el veredicto al final de `RunResult.results`, después de
  todos los demás agentes — sin cambiar ese orden.

## Fuera de alcance / backlog
- **Dashboard visual histórico** — `dashboard.py` ya existe en el bundle, se conecta cuando
  haga falta ver muchos runs juntos.
- **Publicación del veredicto** — depende de writers que no existen todavía.
