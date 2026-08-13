# 010 — Agente: performance

## Problema
Cuarto agente del fleet. A diferencia de `datos_prueba`, el bundle no trae scripts
ejecutables para performance — `references/performance.md` es guía pura (qué NFRs pedir,
qué tipo de ensayo, Artillery vs Locust). No hay nada que "minar" en código, solo la
metodología para el prompt.

## Alcance
Cubre CDA-43/44/45 (epic "Sub-agente: Pruebas de performance", CDA-42):
- El LLM genera un Locustfile (Python) a partir del ticket — no Artillery, ver justificación
  abajo.
- Si faltan NFRs obligatorios (objetivo, tráfico esperado, usuarios concurrentes, duración,
  SLA/percentiles, error rate, ventana de ejecución, responsable), el agente NO los inventa
  — los reporta como `pending_items`, igual que `automatizacion` con URLs/selectores
  faltantes.
- Validar que el Locustfile generado sea Python sintácticamente válido (`ast.parse`, mismo
  mecanismo que `automatizacion` — no hay validador dedicado de Locust en el bundle).
- Registrarse en `AGENT_REGISTRY["performance"]`.

**Fuera de esta spec:**
- Artillery (Node.js) — Maestro QA es un proyecto Python; igual que `automatizacion` no
  genera REST Assured salvo pedido explícito, este agente no genera Artillery salvo que CDA
  lo pida como excepción puntual.
- Ejecutar el ensayo de carga — necesita el runtime de Locust, el ambiente real y
  autorización explícita (`performance.md`: nunca contra producción sin aprobación). Este
  agente solo genera el archivo.
- Resultados/métricas post-ejecución (p50/p90/p95/p99, throughput real) — no existen sin una
  ejecución real.

## Diseño

**Por qué Locust y no Artillery:** mismo criterio que `automation.md` aplicado ya en
`automatizacion` — Maestro QA es Python de punta a punta (motor core, agentes, scripts
vendorizados). Artillery exige Node.js, una dependencia de runtime nueva para un solo
agente. Si CDA necesita Artillery en un cliente concreto, es una decisión explícita de esa
integración, no el default.

**Prompt:** instruye con las reglas de `performance.md` — no inventar umbrales, resolver el
host vía `QA_TARGET_ENV`/`QA_<AMBIENTE>_API_BASE_URL` en vez de hardcodearlo (mismo patrón
que `qa_environment.py`), clasificar el ensayo en uno de los 6 tipos (baseline/load/stress/
spike/endurance/volume), y si el mensaje incluye casos ya generados, derivar los flujos
críticos a probar de ahí (`performance.md`: "usar casos funcionales para identificar flujos
críticos", no traducir cada caso funcional a carga).

**Formato de salida:**
```json
{
  "test_type": "baseline|load|stress|spike|endurance|volume",
  "locustfile_filename": "performance/locustfile_<feature>.py",
  "locustfile_code": "...",
  "run_command": "locust -f <archivo> --headless -u <users> -r <spawn-rate> -t <duración>",
  "pending_items": ["NFRs faltantes o supuestos que el LLM tuvo que marcar"]
}
```

**Validación:** `ast.parse(locustfile_code)` — igual que `automatizacion`, sin validador
dedicado propio. Si no es Python válido, se levanta una excepción (el orquestador la
captura).

## Criterios de aceptación
- Con un provider fake que devuelve un Locustfile válido, el agente devuelve un
  `AgentResult` con el código, el comando de ejecución sugerido y el tipo de ensayo.
- Con un provider fake que devuelve código con error de sintaxis, el agente lanza una
  excepción.
- Si el LLM reporta `pending_items` (NFRs faltantes), aparecen en el `content`, no se
  ocultan.
- Cuando el intake incluye casos ya generados (spec 008), el prompt se lo hace explícito al
  LLM como fuente de flujos críticos — sin necesidad de cambiar el orquestador otra vez.

## Fuera de alcance / backlog
- **Artillery** — si CDA lo pide explícitamente para un cliente con stack Node.
- **Ejecución real y métricas** — requiere runtime de Locust, ambiente autorizado y (para
  producción) aprobación explícita que no existen en este contexto.
