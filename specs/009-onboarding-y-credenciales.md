# 009 — Onboarding del proyecto y credenciales propias de Maestro QA

## Problema
Falta un paso previo al orquestador que registre dónde vive la configuración del proyecto
(no solo el ticket a mano) y las credenciales que Maestro QA necesita para operar —
repos, LLM, y más adelante Xray/Jira/Trello. Sin esto, cada integración futura tendría que
reinventar cómo leer sus propias credenciales.

## Alcance
- `onboarding.ensure_project()`: crea/lee `qa-project.yaml` (usando `init_qa_project.py`
  del bundle, sin reimplementar su esquema) y verifica el repo configurado si hay uno
  (`verify_repository.py`).
- `config.py`: catálogo de las variables de entorno propias de Maestro QA (no las del
  proyecto del cliente bajo prueba) + un loader que audita cuáles están configuradas, sin
  nunca exponer sus valores.
- `orchestrator.py` conoce la ruta convencional de `qa-project.yaml` para que cualquier
  llamador (hoy nosotros, después el servidor MCP) sepa dónde está documentado el proyecto.

**Fuera de esta spec — dos motivos distintos:**
1. **No es el mismo problema:** las variables `QA_<AMBIENTE>_*` que audita
   `env_file_manager.py` son del **proyecto del cliente bajo prueba** (frontend/backend de
   CDA o de quien sea el cliente) — un `.env` por cliente, no de Maestro QA. Esta spec cubre
   las credenciales de **Maestro QA mismo** (con qué LLM habla, con qué token escribe a
   Xray/GitHub/etc.). Son dos `.env` con dueños distintos, no se mezclan.
2. **Todavía no hace falta:** descubrimiento de documentación, lectura de tableros de
   tareas, descubrimiento de rutas de ambiente, introspección de base de datos, la
   conversación completa de onboarding pregunta-por-pregunta del `SKILL.md` original — nada
   de esto tiene un consumidor real todavía (Maestro QA no lee tableros, no escribe a bases).
   Se construye cuando el agente que lo necesite exista, no antes.

## Diseño

**Dos catálogos de variables, sin mezclarlos:**
- Del **cliente bajo prueba**: `QA_<AMBIENTE>_FRONTEND_URL`, `..._DB_READ_CONNECTION`, etc.
  — ya resueltos por `qa_environment.py` vendorizado, consumidos por
  `assets/playwright-python/`. No cambia nada acá.
- De **Maestro QA mismo** (nuevo, `.env` propio del proyecto `maestro-qa`):
  `MAESTRO_PROVIDER`/`MODEL`/`API_KEY` (ya existían, spec 001) +
  `MAESTRO_GITHUB_TOKEN` (para CDA-60, todavía backlog), `MAESTRO_JIRA_URL`/`_TOKEN`/`_EMAIL`
  (CDA-59/72, backlog), `MAESTRO_TRELLO_KEY`/`_TOKEN` (CDA-73, backlog). Catalogados en
  `.env.example` en la raíz del repo — cada integración futura solo agrega su fila ahí, no
  inventa su propio mecanismo de config.

**`config.py`:** `load_env_file()` (una función chica, propia, no importada del scaffold de
Playwright — ese vive pensado para copiarse a repos de clientes, no para ser dependencia de
Maestro QA) + `env_status(names: list[str]) -> dict[str, bool]` que solo dice
configurado/no-configurado por nombre, nunca el valor.

**`onboarding.ensure_project()`:**
1. Si no existe `qa-project.yaml`, lo crea con `init_qa_project.py --non-interactive
   --project-name maestro-qa --output qa-project.yaml`.
2. Si el yaml tiene un repo con `url` configurada, corre `verify_repository.py --url ...
   --branch ...` y guarda el `access_status` resultante.
3. Devuelve un reporte: ruta del yaml, estado de cada repo configurado, y
   `env_status()` de las variables propias de Maestro QA catalogadas en `.env.example`.

**Por qué no se corre en cada `run()`:** verificar un repo pega contra la red; hacerlo en
cada ticket sería lento y no cambia entre tickets del mismo proyecto. `ensure_project()` se
llama una vez al iniciar (el futuro servidor MCP, o quien invoque el proceso), no dentro del
loop de `orchestrator.run()`. `orchestrator.py` solo necesita saber el nombre convencional
del archivo (`qa-project.yaml`) para poder referenciarlo si hace falta — no volver a
verificarlo por ticket.

**Seguridad:** nunca se pide un valor de credencial en el chat de esta conversación ni en
ningún prompt de agente — solo el nombre de la variable de entorno. El valor real vive
únicamente en el `.env` local (gitignored, `chmod 600`) o en el proceso.

## Criterios de aceptación
- En un directorio sin `qa-project.yaml`, `ensure_project()` crea uno válido.
- Si el yaml no tiene ningún repo configurado, `ensure_project()` no intenta verificar nada
  (no rompe, no pega contra la red sin necesidad).
- `env_status()` nunca incluye un valor real en su salida, solo `True`/`False` por nombre.
- Los tests no dependen de tener ninguna credencial real configurada.

## Fuera de alcance / backlog
- Documentación, tableros de tareas, rutas de ambiente, introspección de DB, la
  conversación completa de onboarding — se construyen agente por agente, cuando exista el
  consumidor real (ver punto 2 de "Fuera de esta spec").
- Auditoría de `.env` del **cliente** vía `env_file_manager.py` — corresponde al momento en
  que Maestro QA efectivamente toque el repo de un cliente (automatización, CDA-60), no
  antes.
