# 018 — Agente: trazabilidad requisitos↔casos

## Problema
Décimo y último agente del plan original. Es agente **default** (corre siempre, junto con
`casos_manuales`) — su trabajo es la pregunta que nadie más responde: de los requisitos o
criterios de aceptación del ticket, ¿cuáles quedaron realmente cubiertos por los casos que
`casos_manuales` generó, y cuáles no?

## Alcance
Cubre CDA-51/52/53 (epic "Sub-agente: Trazabilidad requisitos↔casos", CDA-50):
- El LLM identifica los requisitos/criterios de aceptación del ticket (explícitos si están
  listados, inferidos si no).
- Cruza cada requisito contra los casos ya generados en el mismo run (spec 008) — a qué
  `case_id`(s) queda asociado.
- El agente (no el LLM) calcula qué requisitos quedaron sin ningún caso asociado — evita
  que el LLM se contradiga diciendo "cubierto" pero sin listar ningún caso.
- Validación estructural propia (sin script vendorizado para esto — el contrato canónico de
  `business_rule_ids`/`work_item_ids` ya lo usa `casos_manuales`, pero cruzarlo contra
  requisitos es trabajo nuevo).
- Registrarse en `AGENT_REGISTRY["trazabilidad"]`.

**Fuera de esta spec:**
- Trazabilidad contra un tablero de tareas real (Jira/Trello) — necesita lectura de tablero,
  que no existe (los writers en backlog son de escritura, no lectura).
- Trazabilidad entre runs — como `regresion`, trabaja con lo que hay en el run actual, no
  con una base histórica que no existe (backlog de spec 004).

## Diseño

**Por qué el cálculo de "sin cubrir" lo hace el código, no el LLM:** si el LLM devolviera
directamente `status: "covered"` además de la lista `covered_by`, podría contradecirse
(marcar "covered" con la lista vacía). Derivar `uncovered` de `covered_by` vacío en Python
elimina esa clase de error por completo — mismo criterio que otros agentes evitan pedirle
al LLM que calcule algo que el código puede calcular determinísticamente.

**Formato de salida del LLM:**
```json
{
  "requirements": [
    {"requirement": "...", "covered_by": ["FE-TC-001", "..."]}
  ],
  "pending_items": ["requisitos ambiguos o no mencionados explícitamente en el ticket"]
}
```

**Validación estructural propia:** `requirements` no vacío, cada entrada con `requirement`
no vacío y `covered_by` como lista (puede estar vacía).

**Resultado:** el `content` muestra una matriz simple — requisito → casos que lo cubren — y
una sección aparte, calculada por código, con los requisitos sin ningún caso asociado.

## Criterios de aceptación
- Con casos ya generados en el mismo run, el agente asocia correctamente cada requisito a
  los `case_id` que lo cubren.
- Un requisito con `covered_by` vacío aparece en la sección de sin cobertura, calculada por
  código, no reportada por el LLM.
- Sin casos generados (agente corrido solo), todos los requisitos quedan sin cobertura —
  se reporta, no rompe.
- `requirements` vacío levanta una excepción.

## Fuera de alcance / backlog
- **Trazabilidad contra un tablero real** — depende de lectura de Jira/Trello, no existe.
- **Trazabilidad entre runs** — depende de persistencia histórica (backlog de spec 004).
