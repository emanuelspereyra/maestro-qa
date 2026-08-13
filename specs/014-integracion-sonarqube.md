# 014 — Integración con SonarQube (lectura de hallazgos)

## Problema
`seguridad` (spec 013) genera casos a partir del ticket, sin evidencia real de la
aplicación. Si CDA ya tiene un servidor SonarQube/SonarCloud corriendo contra el código de
un cliente, esos hallazgos (vulnerabilidades, security hotspots) son evidencia real que hoy
se ignora.

## Alcance
- `sonarqube.fetch_findings()`: lee vulnerabilidades abiertas y security hotspots
  pendientes de revisión vía la API REST de SonarQube (self-hosted o SonarCloud, misma
  API). No dispara un análisis nuevo — solo lee resultados ya calculados.
- `seguridad` los usa como contexto adicional si están configurados — nunca los inventa, ni
  rompe si no están configurados o si la consulta falla.
- Config propia de Maestro QA (spec 009): `MAESTRO_SONARQUBE_URL`,
  `MAESTRO_SONARQUBE_TOKEN`, `MAESTRO_SONARQUBE_PROJECT_KEY` en `.env.example`.

**No resuelto todavía (pregunta abierta original de CDA-82):** si CDA no tiene ningún
servidor SonarQube corriendo, esta integración queda configurada pero inerte — no hay nada
que romper, `seguridad` sigue funcionando exactamente igual sin esas variables.

**Fuera de esta spec:**
- Disparar un análisis de SonarQube (`sonar-scanner`) — necesita el repo clonado y el
  proyecto ya dado de alta en SonarQube, no es "leer", es "ejecutar".
- Cualquier otro agente además de `seguridad` consumiendo estos hallazgos.

## Diseño

**Por qué solo lectura:** SonarQube ya resuelve el análisis estático mejor de lo que
haríamos nosotros — el valor de Maestro QA acá es traer esa evidencia al mismo lugar que
las pruebas en runtime, no reimplementar un analizador estático.

**Endpoints usados:** `GET /api/issues/search` (vulnerabilidades, `types=VULNERABILITY`,
`resolved=false`) y `GET /api/hotspots/search` (`status=TO_REVIEW`) — funcionan igual en
SonarQube self-hosted y SonarCloud, mismo contrato de API. Autenticación por token vía
HTTP Basic (usuario=token, password vacía), estándar de SonarQube.

**Tolerancia a fallos:** si las variables no están configuradas, o la consulta falla (red,
auth, proyecto inexistente), `seguridad` simplemente no incluye contexto de SonarQube —
no lo trata como error del agente. Mismo criterio que el historial de ejecución (spec 006):
una integración de evidencia no debe tumbar el trabajo real.

**Inyección de contexto:** un resumen corto (conteo por severidad, primeros hallazgos) se
antepone al mensaje del usuario que recibe el LLM de `seguridad`, con una etiqueta clara
("Hallazgos reales de SonarQube:") para que el LLM los distinga del ticket.

## Criterios de aceptación
- `fetch_findings()` con un cliente HTTP fake (sin red real) devuelve vulnerabilidades y
  hotspots ya simplificados.
- Si la consulta HTTP falla, `fetch_findings()` levanta `SonarQubeError` — y `seguridad`
  lo captura sin romper la generación de casos.
- Sin las 3 variables de entorno configuradas, `seguridad` se comporta exactamente igual
  que antes de esta spec.
- Ningún test depende de un servidor SonarQube real.

## Fuera de alcance / backlog
- **Disparar análisis nuevo** — requiere repo clonado + `sonar-scanner`, otro nivel de
  integración.
- **Otros agentes consumiendo estos hallazgos** — se agrega si hay un caso de uso real.
