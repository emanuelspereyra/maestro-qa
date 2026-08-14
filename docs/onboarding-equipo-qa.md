# Onboarding — Maestro QA para el equipo de QA de CDA

Esta guía es para vos, que vas a usar Maestro QA día a día con tickets reales — no para
quien lo instala (eso está en el [README](../README.md)).

## Qué es

Maestro QA toma un ticket de Jira (o una spec/PRD) y te devuelve, en un solo resultado:
casos de prueba manuales, automatización cuando corresponde, datos de prueba, un borrador
de priorización de bugs, y varios chequeos más — cada uno hecho por un agente
especializado. No reemplaza tu criterio: genera un punto de partida sólido y señala
explícitamente lo que no pudo resolver solo, en vez de inventarlo.

## Cómo lo usás

Maestro QA corre dentro de tu asistente de IA ya configurado (Claude Code, GitHub Copilot
o Codex CLI — quien te lo instaló ya dejó esto funcionando). No hace falta un comando
especial: le pedís en lenguaje natural que corra Maestro QA sobre tu ticket, por ejemplo:

> Corré Maestro QA sobre este ticket:
>
> [pegás el texto completo del ticket de Jira acá]

Tu asistente reconoce que tiene que usar la tool `run_qa` y te devuelve el resultado
agregado de todos los agentes que aplicaron a ese ticket. Cuantos más detalles tenga el
ticket (criterios de aceptación, ambiente, qué se rompe si falla), mejor el resultado —
Maestro QA nunca inventa un dato que falta, lo marca como pendiente.

Si es tu primera vez en un proyecto nuevo, pedile primero que corra `ensure_project` —
te dice qué credenciales/repos están configurados antes de arrancar con tickets.

**Si el proyecto tiene Azure DevOps conectado**, no hace falta ni copiar el texto del
ticket — le pasás el ID del work item:

> Corré Maestro QA sobre el work item 4521 de Azure DevOps.

Trae el título y la descripción reales del work item y corre exactamente igual que si
lo hubieras pegado a mano.

## Qué agente hace qué

Dos corren siempre, sin que el ticket los pida:

| Agente | Qué hace |
|---|---|
| `casos_manuales` | Casos de prueba manuales estructurados (pasos, resultado esperado, prioridad). Es la base que el resto de los agentes reusa. |
| `trazabilidad` | Cruza los criterios de aceptación del ticket contra los casos generados — te dice qué está cubierto y qué quedó como hueco. |

El resto se activa según lo que el ticket menciona (palabras clave — no hace falta que
las digas exactas, alcanza con que el ticket hable naturalmente del tema):

| Agente | Se activa si el ticket habla de... | Qué te devuelve |
|---|---|---|
| `automatizacion` | automatizar, e2e, CI/CD | Page Object + test Playwright (frontend) |
| `automatizacion_api` | endpoint, API REST, backend | Cliente HTTPX + test pytest (backend) |
| `datos_prueba` | datos de prueba, dataset, carga masiva | Un dataset generado de forma determinística (mismo seed = mismos datos) |
| `performance` | performance, prueba de carga, estrés, latencia | Un locustfile listo para correr |
| `priorizacion_bugs` | bug, defecto, incidencia, hotfix | Borrador de defecto — severidad técnica sugerida, la prioridad de negocio siempre queda "pendiente de decisión de negocio" |
| `seguridad` | seguridad, vulnerabilidad, OWASP, permisos | Casos de seguridad tipo OWASP (y hallazgos de SonarQube si el proyecto lo tiene conectado) |
| `documentacion` | documentar, manual de usuario | Changelog / guía de usuario / referencia técnica según lo que el ticket pida |
| `regresion` | regresión, suite completa | Qué áreas ya cubiertas por casos anteriores hay que re-verificar por este cambio |
| `calidad_codigo` | revisar código, code review, refactor | Revisión de sobre-ingeniería/código innecesario — ver más abajo |

Y al final de todo corre **`release_readiness`**: lee el resultado de todos los demás y te
da un veredicto — `GO`, `GO_WITH_CONDITIONS` o `NO_GO` — con el motivo. Si algún agente
falló durante la corrida, el veredicto nunca es `GO` aunque el texto lo sugiera: Maestro QA
lo corrige solo.

## Cómo leer el resultado

- **Empezá por `release_readiness`** — es el resumen ejecutivo. Si dice `NO_GO` o
  `GO_WITH_CONDITIONS`, ahí tenés el motivo antes de mirar el detalle de cada agente.
- **`## Pendiente`** en cualquier agente no es un error — es Maestro QA diciéndote
  explícitamente "esto no lo pude resolver con lo que tenía, no lo inventé". Son los
  puntos que necesitan que vos (o quien escribió el ticket) completen un dato real:
  una URL, un selector, un SLA, un contrato de API.
- Si un agente aparece marcado **(error)**, algo salió mal en esa corrida puntual (no
  tira abajo el resto) — normalmente un problema de conexión con el proveedor de IA, no
  algo que tengas que resolver vos. Si se repite, avisá.

## Automatización: qué hacer con el código generado

`automatizacion`/`automatizacion_api` te devuelven código Python (Playwright o
pytest+HTTPX). Qué hacer con ese código depende de cómo esté configurado el proyecto:

- **Sin ningún repo conectado**: copialo vos mismo al proyecto de automatización
  correspondiente y corré los tests como siempre.
- **Con `repositories.frontend` conectado**: además de generar el código, el agente
  explora ese repo real y, si le falta un selector estable a un componente, le agrega un
  `data-testid` **directamente en el código real** — pero solo en una rama local nueva
  (`automatizacion/<feature>-<fecha>`), con un commit, **nunca la sube ni abre un PR**.
  Si ves la sección "Cambios en el repo de frontend", andá al path que te indica, revisá
  el diff, y subilo vos mismo si te parece bien.
- **Con `repositories.automation` conectado** (un repo separado para los scripts de
  test, no el de la app): el Page Object/test o cliente API/test que se generó se lleva
  a ese repo de verdad — rama nueva, commit, **y esta vez sí se pushea y se abre un PR
  real** (si es GitHub). Vas a ver la sección "Repo de automatización" con el link del
  PR listo para revisar. **Nunca se mergea solo** — el merge lo hacés vos como cualquier
  otro PR.

## `calidad_codigo`: revisión anti sobre-ingeniería

Este agente no genera nada nuevo — revisa código real (pegado en el ticket, el repo de
frontend conectado, o lo que `automatizacion`/`automatizacion_api` acaban de generar en el
mismo ticket) buscando patrones típicos de código sin revisar: abstracciones que no hacen
falta, validación de casos imposibles, comentarios que repiten el código, helpers que
reinventan algo que el lenguaje ya resuelve. Es de **solo lectura** — nunca modifica nada,
ni siquiera cuando tiene acceso al repo real.

Pedilo explícitamente ("revisar código", "code review") cuando quieras una segunda opinión
sobre algo que se generó o que ya existe. Si no encuentra nada, te lo dice — no inventa
hallazgos para justificar la corrida.

También podés correrlo solo, sobre un archivo o diff puntual, sin pasar por un ticket
completo — pedile a quien lo instaló el comando exacto (`scripts/revisar_codigo.py`).

## Casos publicados en Azure DevOps (si está conectado)

Si el proyecto tiene esto configurado, `casos_manuales` publica automáticamente cada
caso que genera como un work item — vas a ver una sección "Casos publicados" con el link
de cada uno. Si algún caso puntual no se pudo publicar, aparece en "Pendiente" con el
motivo, sin afectar a los demás. Sin esta integración conectada, los casos siguen
apareciendo igual que siempre, solo en el resultado de texto.

## Preguntas frecuentes

**¿Por qué no generó automatización si mi ticket es claramente de un flujo E2E?**
Rutea por palabras clave del texto del ticket — si no menciona nada relacionado
("automatizar", "e2e", "CI/CD"), no se activa. Agregá una frase explícita si lo necesitás
("hay que automatizar este flujo").

**¿Puedo confiar en los datos de prueba tal cual, o son reales?**
Son generados, nunca reales — `datos_prueba` deja explícito `GENERATED_NOT_INSERTED` en
el resultado. Sirven para completar un test, no para producción.

**El veredicto de `priorizacion_bugs` dice la prioridad de negocio, ¿está mal?**
No — ese campo siempre queda fijo en "pendiente de decisión de negocio" a propósito, el
agente nunca decide eso por vos. La severidad técnica sí la sugiere.

**¿A quién le pregunto si algo no anda?**
A quien te instaló Maestro QA (hoy, Emanuel) — puede ser un problema de configuración
(credenciales, repo conectado) más que del ticket en sí.
