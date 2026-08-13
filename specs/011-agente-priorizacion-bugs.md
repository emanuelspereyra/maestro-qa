# 011 — Agente: priorización/triage de bugs

## Problema
Quinto agente del fleet. Igual que `performance`, el bundle no trae un script ejecutable
para esto — `references/execution.md` (secciones "Defectos", "Severidad", "Publicación") es
guía pura. La pieza a construir es el prompt + una validación estructural propia, no un
wrapper de un script existente.

## Alcance
Cubre CDA-31/32/33 (epic "Sub-agente: Priorización/triage de bugs", CDA-30):
- El LLM redacta un **borrador** de defecto a partir del ticket (o de un caso fallido), con
  severidad sugerida y prioridad de negocio por separado.
- Validación estructural propia (sin script vendorizado — no existe uno para esto): campos
  obligatorios presentes, severidad y reproducibilidad dentro de valores válidos.
- El agente es honesto sobre lo que NO puede hacer todavía: no busca duplicados reales (no
  hay conexión de lectura a ningún tracker) y no publica nada (los writers de Xray/Jira
  siguen en backlog, CDA-59/72). Lo dice explícito en el resultado, no lo oculta.
- Registrarse en `AGENT_REGISTRY["priorizacion_bugs"]`.

**Fuera de esta spec:**
- Búsqueda real de duplicados contra un tracker — necesita lectura de Xray/Jira/Trello, que
  no existe (los writers en backlog son de escritura, no de lectura).
- Publicación real del defecto — necesita los writers de CDA-59/72/73/74, todos en backlog.
- Tendencias/impacto entre múltiples defectos — necesita historial acumulado de varios runs,
  no un ticket individual.

## Diseño

**Por qué severidad y prioridad de negocio separadas:** `execution.md` lo pide explícito
("Separar severidad técnica de prioridad de negocio") — severidad es sobre el impacto
técnico (Critical/High/Medium/Low según las definiciones del bundle), prioridad de negocio
es una decisión que el equipo/producto toma después, no algo que el agente deba decidir por
ellos. El agente sugiere severidad; prioridad de negocio queda como campo abierto para que
alguien la complete, no la inventa.

**Prompt:** instruye con el contrato de "Defectos" (título, caso y fuente, ambiente y
versiones, precondiciones, datos usados, pasos, resultado esperado/obtenido,
reproducibilidad, severidad sugerida, evidencia requerida) y las 4 categorías de severidad.
Si el mensaje incluye casos ya generados (spec 008) y alguno describe un fallo, el agente
usa ESE caso como fuente en vez de inventar un escenario nuevo.

**Formato de salida:**
```json
{
  "title": "...",
  "case_id_o_fuente": "...",
  "ambiente_y_versiones": "...",
  "preconditions": ["..."],
  "datos_usados": "...",
  "steps": ["..."],
  "expected_result": "...",
  "actual_result": "...",
  "reproducibility": "siempre|intermitente|no_reproducido",
  "severity": "Critical|High|Medium|Low",
  "business_priority": "pendiente de decisión de negocio",
  "evidence_required": ["..."]
}
```

**Validación estructural propia** (no hay script del bundle para esto): campos obligatorios
presentes y no vacíos, `severity` uno de los 4 valores válidos, `reproducibility` uno de los
3 valores válidos. Si falla, se levanta una excepción (el orquestador la captura).

**Resultado:** el `content` arranca con una advertencia explícita — "Borrador sin duplicados
verificados ni publicación real" — antes del detalle, para que nadie confunda esto con un
bug ya cargado en un tracker.

## Criterios de aceptación
- Con un provider fake que devuelve un borrador válido, el agente devuelve el `AgentResult`
  con la advertencia de borrador + todos los campos.
- Con severidad o reproducibilidad fuera de los valores válidos, el agente lanza una
  excepción.
- El resultado nunca afirma que se buscaron duplicados o que se publicó algo.

## Fuera de alcance / backlog
- **Duplicados reales y publicación** — dependen de integraciones de lectura/escritura que
  no existen todavía (ver Alcance).
- **Tendencias entre defectos** — necesita agregación entre runs, no valor en un ticket
  individual.
