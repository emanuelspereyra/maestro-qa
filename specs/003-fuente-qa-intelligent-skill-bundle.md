# 003 — Fuente externa: qa-intelligent-skill-bundle

## Problema
Emanuel ya tenía armado un skill de Codex/ChatGPT (`generate-qa-from-test-cases` +
`start-qa`, formato `openai.yaml`) con metodología QA madura y ~7200 líneas de scripts
Python. Implementar los 10 agentes de Maestro QA sin mirar esto sería reinventar trabajo
ya hecho y probado.

## Alcance
Documentar qué trae `vendor/qa-intelligent-skill-bundle/` y a qué agente de Maestro QA le
corresponde, para consultarlo *antes* de escribir la spec de cada agente (CDA-18 a CDA-57).
No define código nuevo — es un mapa de fuentes.

## Diseño

**Por qué no se integra tal cual:** el bundle está pensado para que un agente Codex/ChatGPT
siga sus instrucciones en lenguaje natural turno a turno (onboarding conversacional,
confirma antes de escribir, etc.) e invoque sus scripts como CLI. No implementa el contrato
`Agent.run(intake, provider) -> AgentResult` de `agents/registry.py` (spec 002) ni corre
como servidor MCP. Migrarlo tal cual sería forzar un formato de invocación (`$skill-name`,
`agents/openai.yaml`) que no existe en Claude Code ni en Copilot.

**Qué sí se reutiliza directo, sin reescribir:**
- Los scripts (`scripts/*.py`) son CLIs Python independientes del framework que los llama.
  Cada agente de Maestro QA puede invocarlos como subproceso en vez de reimplementar su
  lógica.
- Los `references/*.md` son la metodología QA en sí — se usan como fuente del prompt/
  system message de cada agente, no como código.
- `assets/playwright-python/` es un scaffold de automatización listo para copiar al repo
  del cliente cuando el agente de automatización lo necesite.

**Mapa fuente → agente:**

| Agente Maestro QA | Referencias | Scripts | Assets |
|---|---|---|---|
| `casos_manuales` | test-design.md, comprehensive-coverage.md, discovery.md, task-boards.md, onboarding.md | validate_cases.py, render_manual_cases.py | test-case.template.json, manual-test-case.template.md |
| `automatizacion` (POM) | automation.md | — | playwright-python/ (conftest.py, base_page.py, qa_environment.py, pyproject.toml) |
| `datos_prueba` | data.md, external-service-mocking.md | generate_dataset.py, data_inventory.py, mock_api_server.py | dataset-spec.template.json, third-party-mock.template.json |
| `priorizacion_bugs` | execution.md (sección defectos) | qa_history.py | — |
| `documentacion` | *(hueco — el bundle no cubre esto)* | — | — |
| `regresion` | comprehensive-coverage.md | qa_history.py | — |
| `performance` | performance.md | — | — |
| `seguridad` | *(hueco — el bundle solo cubre manejo seguro de secretos, no testing de seguridad)* | — | — |
| `trazabilidad` | test-design.md (contrato canónico: business_rule_ids, work_item_ids), task-boards.md | — | — |
| `release_readiness` | audit-dashboard.md | dashboard.py, qa_history.py | — |
| *(infraestructura, no un agente)* | environment-files.md, gitignore.md | env_file_manager.py, gitignore_manager.py, preflight.py, verify_repository.py, discover_environment_routes.py | environment-routes.template.json |

## Criterios de aceptación
- Antes de escribir la spec de cualquiera de los 10 agentes, se revisó la fila
  correspondiente de esta tabla.
- Si un script del bundle se reutiliza en un agente, la spec de ese agente lo referencia
  explícitamente en vez de reimplementar la misma lógica.

## Fuera de alcance / backlog
- `documentacion` y `seguridad` no tienen fuente en el bundle — sus specs se escriben desde
  cero cuando les toque el turno.
- No se adapta el bundle para correr como skill de Claude Code/Copilot — se lo trata
  exclusivamente como fuente de metodología y utilidades, consumido por Maestro QA.
