# 017 — Agente: plan de regresión

## Problema
Noveno agente del fleet. Corrección al mapeo de spec 003: la fuente real de `regresion` no
es `comprehensive-coverage.md` (eso ya lo usa `casos_manuales`) sino la sección "Análisis de
cambios" de `automation.md` — "comparar rutas, endpoints, schemas... proponer suites
afectadas con explicación." Ese es el trabajo real de este agente: decidir **qué ya
cubierto se ve afectado por un cambio**, no generar casos nuevos (eso es `casos_manuales`)
ni ejecutar nada (no hay runner real en este proyecto).

## Alcance
Cubre CDA-39/40/41 (epic "Sub-agente: Plan y ejecución de regresión", CDA-38):
- El LLM identifica qué áreas cambiaron según el ticket (endpoints, rutas, modelos,
  módulos) y decide cuáles de los casos ya generados en el mismo run (spec 008) quedan
  afectados, con motivo.
- Señala huecos: áreas que cambiaron pero ningún caso generado las cubre.
- Sugiere una prioridad de regresión (`full`/`targeted`/`smoke`), no ejecuta nada.
- Validación estructural propia (sin script vendorizado para esto).
- Registrarse en `AGENT_REGISTRY["regresion"]`.

**Por qué depende de los casos ya generados y no de un historial persistente:** no existe
todavía una base de casos de runs anteriores (spec 004 dejó eso en backlog explícito). Este
agente trabaja con lo que hay disponible ahora — los casos del mismo run, encadenados por
spec 008 — no inventa una suite histórica que no existe.

**Fuera de esta spec:**
- Selección de regresión contra una suite histórica real — necesita que `casos_manuales`
  persista sus artefactos entre runs (backlog de spec 004), no existe todavía.
- Ejecutar la regresión — no hay runner de automatización real conectado (backlog de
  `automatizacion`/`automatizacion_api`).

## Diseño

**Prompt:** identifica las áreas de cambio descritas en el ticket. Si el mensaje incluye
"Casos de prueba ya generados" (spec 008), cruza cada caso contra esas áreas: afectado
(con motivo) o no afectado. Si un área de cambio no tiene ningún caso que la cubra, se
reporta como hueco de cobertura — no se inventa un caso ahí (eso es trabajo de
`casos_manuales`, no de este agente).

**Formato de salida:**
```json
{
  "changed_areas": ["..."],
  "affected_cases": [{"case_id": "...", "reason": "..."}],
  "coverage_gaps": ["áreas cambiadas sin ningún caso que las cubra"],
  "regression_priority": "full|targeted|smoke",
  "pending_items": ["información faltante sobre el cambio, puede estar vacía"]
}
```

**Validación estructural propia:** `changed_areas` no vacío, `regression_priority` uno de
los 3 valores válidos, cada entrada de `affected_cases` con `case_id` y `reason`.

## Criterios de aceptación
- Con casos ya generados en el mismo run y un ticket de cambio, el agente cruza
  correctamente cuáles quedan afectados.
- Sin casos generados (agente corrido solo), `affected_cases` queda vacío y el ticket se
  reporta igual con sus `changed_areas`/`coverage_gaps` — no rompe.
- `regression_priority` fuera de los 3 valores válidos levanta una excepción.

## Fuera de alcance / backlog
- **Suite histórica real** — depende de persistir los casos de `casos_manuales` entre runs
  (backlog de spec 004).
- **Ejecución de la regresión** — depende de un runner real conectado.
