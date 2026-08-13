# 012 — Agente: automatización de API (backend)

## Problema
Sexto agente del fleet, sacado del backlog (CDA-78) tras evaluar REST Assured vs
pytest+HTTPX. `automatizacion` (spec 005) quedó scoped solo a frontend/Playwright — nadie
genera automatización de backend todavía.

## Alcance
Cubre CDA-79/80/81 (epic "Sub-agente: Automatización API (backend)", CDA-78):
- Generar un cliente de API (HTTPX) + un test pytest a partir del ticket, siguiendo
  `references/automation.md` sección "APIs en Python".
- Validar sintaxis Python (`ast.parse`, mismo mecanismo que `automatizacion`/`performance` —
  tampoco hay validador dedicado para esto en el bundle).
- Registrarse en `AGENT_REGISTRY["automatizacion_api"]`.

**Decisión ya tomada (no se re-evalúa en esta spec):** pytest + HTTPX, no REST Assured —
mismo criterio "Python de punta a punta" de `automatizacion` (Playwright) y `performance`
(Locust). Documentado en la descripción de CDA-78.

**Fuera de esta spec:**
- REST Assured — excepción puntual si un cliente concreto de CDA lo exige explícitamente,
  no el default.
- Ejecutar el test generado contra una API real — necesita el ambiente y credenciales reales
  que no existen en este contexto (mismo motivo que `automatizacion`).

## Diseño

**Prompt:** instruye con las reglas de `automation.md`/"APIs en Python": HTTPX (no
`requests`, para no sumar una dependencia nueva sin necesidad — HTTPX ya cubre sync/async),
resolver `API_BASE_URL` vía la fixture `api_base_url` que ya existe en el `conftest.py`
vendorizado (spec 003) en vez de hardcodear una URL, validar status/schema/headers
relevantes/errores/autorización, nunca loguear `Authorization` ni cuerpos sensibles. Si el
mensaje incluye casos ya generados (spec 008) con `layer: "backend"`, automatiza esos
`steps` reales en vez de inventar un flujo nuevo — mismo patrón que `automatizacion` y
`performance`.

**Formato de salida:**
```json
{
  "api_client_filename": "clients/<feature>_client.py",
  "api_client_code": "...",
  "test_filename": "tests/test_<feature>_api.py",
  "test_code": "...",
  "pending_items": ["endpoints, contratos o datos que faltaron y no se inventaron"]
}
```

**Validación:** `ast.parse()` sobre ambos bloques, igual que `automatizacion`. Sin
ejecución real.

## Criterios de aceptación
- Con un provider fake que devuelve cliente+test válidos, el agente devuelve ambos bloques
  sin excepción.
- Con código con error de sintaxis, el agente lanza una excepción indicando cuál archivo
  falló.
- `pending_items` se muestra explícito en el resultado, no se oculta.
- Cuando el intake incluye casos backend ya generados, el prompt los usa como fuente — sin
  cambiar el orquestador (ya generalizado en spec 008).

## Fuera de alcance / backlog
- **REST Assured** — excepción puntual bajo pedido explícito de un cliente.
- **Ejecución real y verificación de persistencia** — requiere ambiente y credenciales
  reales.
