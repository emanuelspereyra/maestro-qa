# 017 — Agente: plan de regresión

## Problema
Noveno agente. `regresion` en QA normalmente significa "elegir qué casos de una suite ya
existente re-correr dado un cambio" — pero Maestro QA todavía no persiste una biblioteca de
casos entre runs (`casos_manuales` descarta su JSON canónico al terminar, ver backlog de
spec 004). Sin biblioteca, no hay nada real de donde "seleccionar". Este agente se ajusta a
lo que sí existe hoy: un **plan de regresión por área/alcance**, no una selección de
case_ids de una suite que no existe.

## Alcance
Cubre CDA-39/40/41 (epic "Sub-agente: Plan y ejecución de regresión", CDA-38):
- El LLM identifica áreas afectadas por el cambio descrito en el ticket y recomienda
  alcance de regresión (`full`/`targeted`/`smoke`) con justificación, usando las familias
  de escenario de `comprehensive-coverage.md`.
- Si hay casos ya generados en el mismo run (spec 008), los cita explícitamente como parte
  del alcance afectado — no inventa un case_id de una suite que no existe.
- El seguimiento de ejecución ("execution" del nombre del epic) ya lo cubre el historial
  genérico del orquestador (spec 006 — cada agente, incluido este, ya queda registrado como
  `EXECUTED`/`FAILED` por run) — no se duplica esa lógica acá.
- Validación estructural propia (sin script vendorizado, como `priorizacion_bugs`/
  `seguridad`/`documentacion`).
- Registrarse en `AGENT_REGISTRY["regresion"]`.

**Fuera de esta spec:**
- Selección real de case_ids de una suite persistida — no existe biblioteca todavía. Se
  ajusta cuando `casos_manuales` persista sus casos (backlog de spec 004).
- Ejecutar la regresión — este agente planifica, no corre nada.

## Diseño

**Por qué "plan" y no "selección":** prometer selección exacta de casos sin tener de dónde
seleccionar sería inventar — mejor un plan honesto a nivel de área/alcance, que es lo que
la información disponible (el ticket + los casos del mismo run) realmente permite.

**Formato de salida:**
```json
{
  "change_description": "...",
  "regression_scope": "full|targeted|smoke",
  "affected_areas": ["..."],
  "priority_areas": [
    {"area": "...", "reason": "...", "scenario_families_to_recheck": ["happy-path", "..."]}
  ],
  "out_of_scope_areas": ["área no afectada, con motivo"],
  "pending_items": ["información faltante sobre el alcance real del cambio"]
}
```

**Validación estructural propia:** `regression_scope` en `full`/`targeted`/`smoke`,
`affected_areas` y `priority_areas` no vacíos, cada `priority_area` con `area`/`reason`
completos.

## Criterios de aceptación
- Con un plan válido, el agente devuelve el `AgentResult` con alcance, áreas y prioridades
  legibles.
- Con `regression_scope` inválido o sin áreas, el agente lanza una excepción.
- Cuando el intake incluye casos ya generados, el prompt los cita como parte del alcance
  afectado.

## Fuera de alcance / backlog
- **Selección real de case_ids de una suite persistida** — depende de que
  `casos_manuales` persista sus casos (backlog spec 004).
- **Ejecutar la regresión** — no es trabajo de este agente.
