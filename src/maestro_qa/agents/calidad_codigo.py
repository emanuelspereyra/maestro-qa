import json
from pathlib import Path

from .. import repo_access
from ..json_extraction import extract_json
from ..orchestrator import AgentResult, Intake
from ..providers import Provider
from .registry import AGENT_REGISTRY

_SYSTEM_PROMPT = """Sos un agente de QA que revisa código real en busca de sobre-\
ingeniería y "AI slop" — código generado sin revisión, con patrones típicos: \
abstracciones para un solo uso, validación de escenarios imposibles, helpers que \
reinventan algo que ya existe en el lenguaje/framework, comentarios que repiten lo que \
el código ya dice, scaffolding "para después" que nunca se usa, código muerto. El código \
puede estar en cualquier lenguaje — tu criterio es agnóstico de lenguaje.

Para cada bloque de código relevante preguntate, en este orden, y marcá como hallazgo \
solo lo que no pasa el primer escalón que debería resolverlo:
1. ¿Hace falta que esto exista? (necesidad especulativa = hallazgo)
2. ¿Ya hay un helper/patrón en el mismo código que resuelve esto? (reinventar = hallazgo)
3. ¿Lo resuelve la stdlib/una dependencia ya usada en el proyecto? (código custom
   evitable = hallazgo)
4. ¿La abstracción tiene más de una implementación real, o es una interfaz/config para
   un solo caso? (abstracción prematura = hallazgo)
5. ¿El comentario explica un POR QUÉ no obvio, o repite el QUÉ que el código ya dice?
   (comentario redundante = hallazgo, de severidad baja)

Reglas:
- NO reportes estilo (nombres, formato, líneas en blanco) — eso no es sobre-ingeniería.
- NO inventes hallazgos si el código ya es simple y directo — una lista vacía de \
`findings` es un resultado válido y esperado.
- Si ninguna de las fuentes de código (diff pegado en el mensaje, archivos del repo real, \
código generado por otro agente) tiene contenido real para revisar, no inventes \
hallazgos — decilo en `pending_items`.
- Si tenés acceso a herramientas de exploración del repo (`list_files`/`read_file`), \
usalas para revisar el código real de archivos relevantes, no solo lo que esté pegado en \
el mensaje.

Devolvé EXCLUSIVAMENTE un objeto JSON (sin texto adicional, sin markdown) con estos campos:
{
  "findings": [
    {
      "location": "archivo:línea o descripción del bloque si no hay línea exacta",
      "severity": "alta|media|baja",
      "problem": "qué patrón de sobre-ingeniería/código muerto/abstracción innecesaria se encontró",
      "suggestion": "qué simplificar o eliminar, concreto"
    }
  ],
  "pending_items": ["si no hubo código real para revisar, decirlo acá en vez de inventar hallazgos"]
}
"""

_VALID_SEVERITIES = {"alta", "media", "baja"}
_REQUIRED_FINDING_FIELDS = ["location", "severity", "problem", "suggestion"]


def _validate(payload: dict[str, object]) -> None:
    findings = payload.get("findings")
    if not isinstance(findings, list):
        raise ValueError(  # noqa: TRY004 - convención del proyecto: ValueError para toda validación de input
            "findings debe ser una lista (puede estar vacía)"
        )
    for index, finding in enumerate(findings):
        missing = [field for field in _REQUIRED_FINDING_FIELDS if not finding.get(field)]
        if missing:
            raise ValueError(f"findings[{index}]: faltan campos {', '.join(missing)}")
        if finding["severity"] not in _VALID_SEVERITIES:
            raise ValueError(
                f"findings[{index}]: severity inválida {finding['severity']!r}, "
                f"debe ser una de {sorted(_VALID_SEVERITIES)}"
            )


def _get_repo_access() -> tuple[repo_access.RepoAccess | None, str | None]:
    try:
        return repo_access.get_frontend_repo(Path.cwd() / "qa-project.yaml"), None
    except repo_access.RepoAccessError as exc:
        return None, str(exc)


class CalidadCodigoAgent:
    def run(self, intake: Intake, provider: Provider) -> AgentResult:
        repo, repo_error = _get_repo_access()

        if repo is not None:
            try:
                raw = provider.complete(
                    system=_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": intake.text}],
                    tools=repo_access.READ_ONLY_TOOLS,
                    tool_executor=repo.read_only_executor(),
                )
            except Exception as exc:  # noqa: BLE001 - una falla acá cae a revisar solo lo pegado en el ticket
                repo_error = f"tool-calling falló: {exc}"
                raw = provider.complete(system=_SYSTEM_PROMPT, messages=[{"role": "user", "content": intake.text}])
        else:
            raw = provider.complete(system=_SYSTEM_PROMPT, messages=[{"role": "user", "content": intake.text}])

        payload = json.loads(extract_json(raw, dict))
        _validate(payload)

        findings = payload["findings"]
        if findings:
            sections = [f"{len(findings)} hallazgo(s):"]
            for finding in findings:
                sections.append(
                    f"- **[{finding['severity']}] {finding['location']}**: {finding['problem']}\n"
                    f"  Sugerencia: {finding['suggestion']}"
                )
            content = "\n".join(sections)
        else:
            content = "Sin hallazgos — el código revisado no muestra sobre-ingeniería ni AI slop."

        pending = list(payload.get("pending_items") or [])
        if repo_error:
            pending.append(f"No se pudo usar el repo de frontend ({repo_error}).")
        if pending:
            content += "\n\n## Pendiente\n" + "\n".join(f"- {item}" for item in pending)

        return AgentResult(agent="calidad_codigo", content=content)


AGENT_REGISTRY["calidad_codigo"] = CalidadCodigoAgent()
