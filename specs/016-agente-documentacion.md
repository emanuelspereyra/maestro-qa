# 016 — Agente: documentación

## Problema
Octavo agente del fleet. Como `seguridad` y `priorizacion_bugs`, spec 003 ya marcó
`documentacion` como hueco sin fuente en el bundle — el `references/onboarding.md` del
bundle habla de *descubrir* documentación existente (para hacer QA), no de *generar*
documentación nueva a partir de una feature. Este agente resuelve lo segundo, que es lo que
pide el epic de Linear.

## Alcance
Cubre CDA-35/36/37 (epic "Sub-agente: Documentación", CDA-34):
- El LLM genera un artefacto de documentación (no código) a partir del ticket — típicamente
  lo que un QA termina redactando después de entender una feature lo suficiente para
  probarla: qué hace, comportamiento esperado, casos borde.
- Si el mensaje incluye casos ya generados (spec 008), la documentación se basa en el
  comportamiento que esos casos describen, no en una relectura independiente del ticket.
- Validación estructural propia (como `priorizacion_bugs`/`seguridad` — sin script
  vendorizado para esto).
- Registrarse en `AGENT_REGISTRY["documentacion"]`.

**Fuera de esta spec:**
- Publicar la doc en un wiki/Notion/Confluence real — necesita un writer que no existe
  (mismo patrón que Xray/Jira/Trello, todos en backlog).
- Generar documentación de código (docstrings, comentarios) — eso es responsabilidad de
  quien escribe el código, no de un agente de QA.

## Diseño

**Tipos de documento** (el LLM elige el que corresponda, no genera los 4 siempre):
`changelog` (entrada breve de qué cambió, para release notes), `user_guide` (cómo usar la
feature desde la perspectiva de un usuario final), `technical_reference` (comportamiento y
contrato técnico, para otros devs/QA), `test_plan_summary` (qué se cubrió y qué no, a partir
de los casos generados — el más directamente ligado a QA).

**Prompt:** pide el tipo de documento más adecuado al ticket, con secciones tituladas.
Si hay casos ya generados, la sección de comportamiento/edge-cases se redacta desde esos
casos (`title`, `objective`, `expected_result`) — no se re-inventa el análisis.

**Formato de salida:**
```json
{
  "doc_type": "changelog|user_guide|technical_reference|test_plan_summary",
  "title": "...",
  "summary": "...",
  "sections": [{"heading": "...", "content": "..."}],
  "pending_items": ["información faltante para completar la doc, puede estar vacía"]
}
```

**Validación estructural propia:** `doc_type` dentro de los 4 valores válidos, `title` y
`summary` no vacíos, al menos una sección con `heading` y `content` no vacíos.

## Criterios de aceptación
- Con un provider fake que devuelve un doc válido, el agente devuelve el `AgentResult` con
  título, resumen y todas las secciones legibles.
- Con `doc_type` inválido o sin secciones, el agente lanza una excepción.
- Cuando el intake incluye casos ya generados, el prompt los usa como fuente del
  comportamiento documentado.

## Fuera de alcance / backlog
- **Publicación real** (wiki/Notion/Confluence) — depende de un writer que no existe
  todavía, mismo criterio que Xray/Jira/Trello.
- **Documentación de código** — no es responsabilidad de este agente.
