# 004 — Agente: casos de prueba manuales

## Problema
Es el primer agente que el orquestador corre siempre (spec 002) — sin él no hay ningún
contenido real que agregar. Necesita producir casos de prueba a partir del texto de un
ticket/spec, en un formato que ya sabemos validar y renderizar porque viene de
`vendor/qa-intelligent-skill-bundle` (spec 003).

## Alcance
Cubre CDA-19/20/21 (epic "Sub-agente: Creador de casos de prueba manuales", CDA-18):
- Generar casos con el LLM configurado, en el contrato canónico del bundle.
- Validar la salida con el script ya existente `validate_cases.py` (sin reimplementar el
  esquema).
- Renderizar el formato manual legible con `render_manual_cases.py` (sin reimplementar el
  render).
- Registrarse en `AGENT_REGISTRY["casos_manuales"]`.

**Fuera de esta spec:** los otros 9 agentes, la persistencia a largo plazo de artefactos
(`qa-artifacts/`, historial) — v1 solo necesita que el resultado llegue al reporte del
orquestador, no un dashboard.

## Diseño

**Por qué reusar los scripts del bundle en vez de reimplementar el esquema:** el esquema
canónico (`REQUIRED_FIELDS`, layers, scenario families, etc.) ya está definido y probado en
`validate_cases.py`. Duplicarlo en Python nuestro sería la misma fuente de verdad en dos
lugares — cualquier ajuste futuro al esquema quedaría desincronizado. El agente invoca los
scripts como subprocesos:

```
LLM (provider.complete) → JSON de casos → validate_cases.py → render_manual_cases.py
```

**Prompt:** el system prompt incluye el esquema completo (los mismos campos que
`REQUIRED_FIELDS`) y un ejemplo few-shot tomado directo de
`assets/test-case.template.json`. Se le pide al LLM devolver **solo** un array JSON de
casos — no el objeto completo con `coverage`, eso lo calcula `validate_cases.py`.

**Validación — por qué no se usan las mismas flags que sugiere el SKILL.md original:**
`--require-layers frontend backend` tiene sentido para la entrega completa de un proyecto,
no para un ticket individual que legítimamente puede ser solo backend o solo frontend. El
agente valida:
- `--require-scenarios happy-path unhappy-path boundary` (toda capa presente debe tener como
  mínimo estas 3 familias) — sí se mantiene, es una garantía de calidad por caso, no de
  alcance del proyecto.
- Sin `--strict` — cobertura `PARTIAL` (falta alguna capa) es aceptable para un ticket
  puntual; se informa en el resumen, no bloquea el resultado.
- Si `validate_cases.py` reporta `errors` (JSON estructuralmente inválido — el LLM no siguió
  el contrato), el agente levanta una excepción. El orquestador (spec 002) ya la captura y
  la marca como resultado con error sin abortar a los demás agentes — no hace falta lógica
  de reintento en el agente mismo.

**Ubicación de los scripts vendorizados:** se resuelve con la variable de entorno
`MAESTRO_QA_BUNDLE_SCRIPTS`, con default calculado como ruta relativa al repo
(`vendor/qa-intelligent-skill-bundle/skills/generate-qa-from-test-cases/scripts`). Ver
Backlog sobre el techo de este approach.

**Resultado:** `AgentResult.content` es el resumen de cobertura (`delivery_status`,
conteo de casos, capas) seguido del render legible en español. El JSON canónico se descarta
al salir del directorio temporal — no se persiste todavía (ver Backlog).

## Criterios de aceptación
- Con un provider fake que devuelve casos válidos, el agente devuelve un `AgentResult` con
  el resumen de cobertura y el render legible, sin lanzar excepción.
- Con un provider fake que devuelve JSON con campos faltantes, el agente lanza una
  excepción con los errores de `validate_cases.py` incluidos.
- El esquema de casos no está duplicado en código Python propio — solo vive en
  `validate_cases.py`/`render_manual_cases.py` del bundle vendorizado.

## Fuera de alcance / backlog
- **Persistir el JSON canónico** (`qa-artifacts/casos_manuales/<feature>.json`) para que el
  agente de automatización lo consuma después — hoy el resultado solo vive en el reporte del
  orquestador. Se agrega cuando el agente de automatización lo necesite como input real.
- **Resolución de `MAESTRO_QA_BUNDLE_SCRIPTS` por ruta relativa al repo** — ponytail: rompe
  si el paquete se instala fuera de este repo (ej. como wheel en otro proyecto). Mientras
  todo corra desde este mismo repo, alcanza; el día que haga falta empaquetar el bundle
  junto al wheel, se resuelve moviendo los scripts dentro de `src/maestro_qa/` o
  empaquetándolos como `package_data`.
- **Reintento automático si `validate_cases.py` encuentra errores** — v1 falla y deja que el
  orquestador lo reporte; un loop de auto-corrección con el LLM es una mejora, no un
  requisito para el primer agente funcionando.
