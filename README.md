# Maestro QA

Orquestador multi-agente de testing. Recibe una tarea (ticket de Jira o spec/PRD) y
reparte el trabajo entre agentes especializados (casos manuales, automatización, datos de
prueba, priorización de bugs, regresión, performance, seguridad, trazabilidad,
release-readiness). Se expone como servidor MCP — usable desde Claude Code y GitHub Copilot
sin integración adicional.

Ver [`specs/000-arquitectura.md`](specs/000-arquitectura.md) para el diseño completo.

## Metodología: Spec-Driven Development

Ninguna feature se implementa sin una spec primero. Antes de escribir código:

1. Copiá `specs/TEMPLATE.md` a `specs/NNN-nombre-feature.md`.
2. Completala: problema, alcance, diseño, criterios de aceptación.
3. Implementá contra esa spec. El PR referencia el número de spec.

## Desarrollo

```bash
pip install -e ".[dev]"
ruff check .
mypy src
pytest
```
