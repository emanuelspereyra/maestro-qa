---
name: maestro-qa-fleet-local
description: "Corré el fleet de agentes de Maestro QA vos mismo, en esta sesión, sin pegarle a la API externa (Gemini/Anthropic/etc.) configurada en MAESTRO_PROVIDER — evita el rate limit y el costo de esa API por completo."
version: 1.0.0
---

# Maestro QA — fleet local (sin API externa)

## Por qué existe

`mcp__maestro-qa__run_qa` (y el resto del fleet) corre sobre el `Provider` configurado en `/root/maestro-qa/.env` (`MAESTRO_PROVIDER`/`MAESTRO_MODEL` — hoy `gemini`/`gemini-flash-latest`, gratis pero con rate limit real). Cuando esa API se agota o tira 429, **no hace falta pagar una API key nueva ni esperar el reset**: cada uno de los 13 agentes del fleet es, en el código fuente, solo un `_SYSTEM_PROMPT` (string) + una llamada `provider.complete(system=_SYSTEM_PROMPT, messages=[...])`, más — en algunos casos — un script determinístico de post-proceso que no usa LLM para nada. Vos (la sesión de Claude Code/Codex que está corriendo esto, ya paga/activa) podés ser ese "provider" directamente: leer el prompt real del agente, responder vos mismo con tu propio razonamiento, y correr el mismo script de post-proceso. Cero llamadas a la API externa, cero rate limit, cero costo adicional — el trabajo pasa a ser parte de esta misma conversación.

`ensure_project()` (vía MCP) **no** usa LLM — solo lee/crea `qa-project.yaml`. Seguí usando esa tool tal cual, no hace falta reemplazarla.

## Cómo correr un dominio en modo local

1. Identificá el dominio pedido (ver tabla) y confirmá el path exacto del archivo — el nombre del agente puede tener variantes de escritura en el ticket, la tabla usa la clave real de `AGENT_REGISTRY`.
2. Leé el archivo fuente (`Read` de la tool nativa, no lo adivines de memoria — el prompt puede haber cambiado desde la última vez que lo viste) y extraé el string `_SYSTEM_PROMPT` completo.
3. Actuá vos mismo como ese agente: usá `_SYSTEM_PROMPT` como tu propio marco para este turno, con el texto del ticket/spec (`intake.text` — lo que te haya llegado del pedido de QA) como si fuera el mensaje de usuario. Producí la salida en el schema EXACTO que ese prompt describe (JSON puro, sin markdown ni texto extra, salvo que el prompt pida otra cosa explícitamente).
4. Si el agente tiene un post-proceso determinístico (columna "Post-proceso" de la tabla), corré ese mismo script vos mismo con `Bash`, pasándole tu JSON como el original lo hace (mirá el bloque `subprocess.run(...)` del archivo para la firma exacta de argumentos — no la reinventes).
5. Si el agente tiene acceso a repo (columna "Repo" = sí), no repliques el `repo_access.py` sandboxeado de Maestro QA — usá tus propias tools nativas (`Read`/`Grep`/`Bash(git ...)`) directo sobre el repo real, es estrictamente más simple y más capaz que el sandbox original.
6. Nunca inventes un resultado si no pudiste producirlo (ej. el script de post-proceso falla) — reportá el error tal cual, mismo criterio que ya exige `agents/qa-reviewer.md` § 6.2 para el modo MCP.

## Tabla de agentes (fuente de verdad: `src/maestro_qa/agents/*.py` — esta tabla es un índice, no una copia; si hay duda, leé el archivo)

| Dominio (clave `AGENT_REGISTRY`) | Archivo | Post-proceso determinístico | Acceso a repo |
|---|---|---|---|
| `casos_manuales` | `agents/casos_manuales.py` | `vendor/.../scripts/validate_cases.py` + `render_manual_cases.py` sobre el JSON generado | No |
| `automatizacion` | `agents/automatizacion.py` | — | Sí, si `repositories.frontend` está configurado en `qa-project.yaml` |
| `automatizacion_api` | `agents/automatizacion_api.py` | — | No |
| `datos_prueba` | `agents/datos_prueba.py` | `vendor/.../scripts/generate_dataset.py <spec> --output <dataset>` | No |
| `performance` | `agents/performance.py` | — | No |
| `priorizacion_bugs` | `agents/priorizacion_bugs.py` | — | No |
| `seguridad` | `agents/seguridad.py` | — | No |
| `documentacion` | `agents/documentacion.py` | — | No |
| `regresion` | `agents/regresion.py` | — | No |
| `trazabilidad` | `agents/trazabilidad.py` | — | No (agente default, corre siempre) |
| `release_readiness` | `agents/release_readiness.py` | Corrección determinística: si el prompt te llega con un header "Agentes con error: ..." y vos como LLM devolvés `overall_status: GO`, hay que forzarlo igual a `NO_GO` (nunca confiar en que el LLM lo note solo en texto libre) | No — lee el resumen de los demás agentes de la misma corrida |
| `calidad_codigo` | `agents/calidad_codigo.py` | — | Sí, si hay repo configurado (frontend/backend o el código que generaron `automatizacion`/`automatizacion_api` en la misma corrida) |
| `bug_explorer` | `agents/bug_explorer.py` | — | Sí, si hay repo configurado — si no, hipótesis conceptual con `file`/`line` en `null`, nunca inventar un path/línea que no viste de verdad |

## Cuándo usar esto vs. `mcp__maestro-qa__run_qa`

**Default (2026-08-16, decisión explícita de Emanuel): usá SIEMPRE este modo local, no `run_qa`.** `MAESTRO_PROVIDER=gemini` tiene muy poco cupo de tokens — no es una alternativa para cuando falla, es la vía normal. No esperes un 429/402 para activarlo.

`run_qa` vía MCP queda como modo alternativo, solo si alguien lo pide explícitamente (ej. para comparar contra el fleet "oficial" desacoplado del modelo que lo invoca, que era el requisito de arquitectura original de Maestro QA — Claude Code, Copilot, Gemini CLI, etc. deberían dar el mismo resultado). Si nadie lo pide, no lo uses.

`casos_manuales` corriendo primero y su resultado inyectado como contexto a los demás agentes de contenido (regla del orquestador real) sigue aplicando acá manualmente: corré ese dominio primero y pasale su output a los siguientes como "Casos de prueba ya generados:" en tu propio prompt.
