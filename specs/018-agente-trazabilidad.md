# 018 — Agente: trazabilidad requisitos↔casos

## Problema
Décimo y último agente del plan original de 10. Fuente: `test-design.md` (contrato
canónico ya usa `business_rule_ids`/`work_item_ids` en cada caso) + `task-boards.md`
(matriz `work_item -> business_rule -> feature_id -> layer -> scenario_family -> case_id`).
El trabajo real de este agente es cruzar lo que el ticket pide contra lo que los casos ya
generados realmente cubren — y decir explícito qué quedó sin cubrir.

## Alcance
Cubre CDA-51/52/53 (epic "Sub-agente: Trazabilidad requisitos↔casos", CDA-50):
- El LLM extrae los criterios de aceptación (o reglas de negocio implícitas) del ticket.
- Si el mensaje incluye casos ya generados (spec 008), cruza cada criterio contra los
  `business_rule_ids`/`case_id` de esos casos: cubierto (con qué casos) o hueco.
- Señala casos sin ningún `business_rule_ids` como "no trazables" — un caso que no se puede
  justificar contra ningún requisito es una señal real, no se oculta.
- Validación estructural propia (sin script vendorizado — `validate_cases.py` valida el
  esquema de un caso individual, no la trazabilidad contra el ticket).
- Registrarse en `AGENT_REGISTRY["trazabilidad"]`.

**Fuera de esta spec:**
- Leer un tablero real (Jira/Trello/Linear) para extraer criterios de aceptación
  originales — no hay integración de lectura, solo lo que el texto del ticket ya trae.
- Matriz persistente entre runs — depende de que `casos_manuales` persista sus casos
  (mismo backlog que bloquea a `regresion`, spec 004).

## Diseño

**Prompt:** extraer criterios de aceptación (o reglas implícitas si el ticket no los lista
explícitos, marcando la derivación) del texto del ticket. Si hay casos ya generados,
cruzarlos: cada criterio queda `covered` (con los `case_id` que lo cubren) o `gap` (ningún
caso lo cubre). Casos generados sin `business_rule_ids` se listan aparte como no trazables.

**Formato de salida:**
```json
{
  "acceptance_criteria": [{"id": "AC-1", "text": "..."}],
  "traceability_matrix": [
    {"criterion_id": "AC-1", "case_ids": ["FE-TC-001"], "status": "covered|gap"}
  ],
  "untraceable_cases": ["case_ids generados sin business_rule_ids, puede estar vacía"],
  "pending_items": ["información faltante, puede estar vacía"]
}
```

**Validación estructural propia:** `acceptance_criteria` no vacío (si el ticket no trae
ninguno explícito, el LLM deriva al menos uno y lo marca en `pending_items` — no se permite
una lista vacía silenciosa), cada entrada de `traceability_matrix` con `criterion_id` y
`status` válido (`covered`/`gap`).

## Criterios de aceptación
- Con casos ya generados que cubren un criterio, la matriz lo marca `covered` con los
  `case_id` correctos.
- Sin casos generados, todos los criterios quedan `gap` — no se inventa cobertura que no
  existe.
- `status` fuera de `covered`/`gap` levanta una excepción.
- Casos sin `business_rule_ids` aparecen en `untraceable_cases`, no se ocultan.

## Fuera de alcance / backlog
- **Lectura real de tableros** — depende de integraciones que no existen.
- **Matriz persistente entre runs** — depende de que `casos_manuales` persista casos
  (backlog de spec 004).
