# 013 — Agente: seguridad

## Problema
Séptimo agente del fleet. A diferencia de casi todos los anteriores, **no hay fuente en el
bundle vendorizado** — spec 003 ya marcó esto como hueco real: `references/` solo cubre
manejo seguro de credenciales *del propio proceso de QA* (no pedir secretos en chat,
sanitizar logs), no metodología para generar casos de seguridad sobre la app bajo prueba.
Este agente parte de cero.

## Alcance
Cubre CDA-47/48/49 (epic "Sub-agente: Pruebas de seguridad", CDA-46):
- El LLM genera **casos de prueba de seguridad** (no código ejecutable) sobre categorías
  tipo OWASP, aplicables solo a lo que el ticket describe — no fuerza las 7 categorías en
  cada feature.
- Validación estructural propia (como `priorizacion_bugs` — no hay script vendorizado para
  esto tampoco).
- Registrarse en `AGENT_REGISTRY["seguridad"]`.

**Por qué casos, no código:** los demás agentes de automatización generan código porque
automatizan un caso ya definido y verificable (`automatizacion`, `automatizacion_api`,
`performance`). Generar código de explotación (payloads de inyección, bypass de auth) sin
un caso previo ni contexto real de la app es más zona gris — se prefiere que este agente
entregue **casos revisables por un humano** (igual que `casos_manuales`), no scripts que se
ejecuten solos. Automatizar esos casos de seguridad, si se necesita, es trabajo de
`automatizacion_api`/`automatizacion` a partir de un caso ya generado — no de este agente.

**Fuera de esta spec:**
- Generar payloads de explotación ejecutables o scripts de pentesting — fuera de alcance por
  la razón anterior.
- Escaneo automático de dependencias/CVEs conocidos — necesita herramientas externas (ej.
  `pip-audit`, `npm audit`) no integradas todavía.

## Diseño

**Categorías** (aplicar solo las relevantes al ticket, no todas siempre):
`broken-access-control`, `broken-authentication`, `injection`, `sensitive-data-exposure`,
`security-misconfiguration`, `rate-limiting-and-dos`, `ssrf`.

**Prompt:** para cada categoría aplicable, un caso con objetivo, pasos (puede incluir un
payload de prueba estándar y conocido, ej. `' OR '1'='1` para probar inyección — no un
exploit real, es la señal de prueba habitual en cualquier checklist de seguridad), resultado
esperado (el comportamiento SEGURO esperado) y severidad si el caso falla. Si el mensaje
incluye casos ya generados (spec 008), usarlos para decidir qué categorías aplican (ej. si
hay un caso de login, `broken-authentication` y `broken-access-control` son relevantes; si
una feature acepta una URL, `ssrf` aplica) — no inventar features nuevas.

**Formato de salida:**
```json
{
  "cases": [
    {
      "category": "broken-access-control|broken-authentication|injection|sensitive-data-exposure|security-misconfiguration|rate-limiting-and-dos|ssrf",
      "title": "...",
      "objective": "...",
      "steps": ["..."],
      "expected_result": "...",
      "severity_if_fails": "Critical|High|Medium|Low"
    }
  ],
  "pending_items": ["categorías que aplicarían pero faltó información para escribir el caso"]
}
```

**Validación estructural propia:** cada caso con campos completos, `category` y
`severity_if_fails` dentro de los valores válidos. Mismo mecanismo que `priorizacion_bugs`.

## Criterios de aceptación
- Con un provider fake que devuelve casos válidos en 2-3 categorías, el agente devuelve el
  `AgentResult` con todos los casos legibles.
- Con una categoría o severidad inválida, el agente lanza una excepción.
- El agente no genera código ejecutable en ningún campo de su salida.
- Cuando el intake incluye casos ya generados con un flujo de login, el prompt lo usa para
  justificar por qué aplican `broken-authentication`/`broken-access-control`.

## Fuera de alcance / backlog
- **Automatizar estos casos** — trabajo de `automatizacion`/`automatizacion_api` a partir
  de un caso de seguridad ya generado, no de este agente.
- **Escaneo de dependencias/CVEs** — necesita herramientas externas no integradas.
