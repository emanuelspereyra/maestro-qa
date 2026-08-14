import json
from pathlib import Path

from .. import repo_access
from ..json_extraction import extract_json
from ..orchestrator import AgentResult, Intake
from ..providers import Provider
from .registry import AGENT_REGISTRY

_SYSTEM_PROMPT = """Sos un agente de QA que traza la descripción de un bug a su causa \
probable en el código real — no lo arreglás, no lo ejecutás, solo razonás sobre el \
código estático para señalar dónde está probablemente el problema.

Leé la descripción del bug con cuidado: síntoma, pasos para reproducirlo, resultado \
esperado vs. resultado real. Si tenés acceso a herramientas de exploración del repo \
(`list_files`/`read_file`), usalas para buscar el código relacionado (por nombre de \
componente, endpoint, mensaje de error, etc.) antes de proponer una causa.

Reglas obligatorias:
- Si tenés acceso al repo real y encontraste el código relacionado, la causa probable \
lleva `file`/`line` reales de lo que leíste — NUNCA inventes un path o número de línea \
que no viste de verdad.
- Si NO tenés acceso al repo real, o no encontraste nada concreto, proponé la hipótesis \
en términos conceptuales (`file` y `line` en `null`, ej. "probablemente en el handler de \
submit del formulario de login") — nunca fabriques un path falso para parecer más \
preciso.
- Si la descripción del bug no tiene ni síntoma ni pasos suficientes para proponer \
ninguna hipótesis, ni siquiera conceptual, decilo en `pending_items` en vez de adivinar \
al azar.
- Podés proponer más de una causa probable si hay ambigüedad real — ordená por \
`confidence` descendente.

Devolvé EXCLUSIVAMENTE un objeto JSON (sin texto adicional, sin markdown) con estos campos:
{
  "likely_causes": [
    {
      "file": "path/al/archivo.py o null si es conceptual",
      "line": 42,
      "confidence": "alta|media|baja",
      "reasoning": "por qué se sospecha este lugar",
      "suggested_direction": "qué revisar/cambiar — no un fix aplicado, puede ser null"
    }
  ],
  "pending_items": ["si no se pudo proponer ninguna hipótesis, o falta info del bug"]
}
"""

_VALID_CONFIDENCES = {"alta", "media", "baja"}
_REQUIRED_CAUSE_FIELDS = ["confidence", "reasoning"]


def _validate(payload: dict[str, object]) -> None:
    causes = payload.get("likely_causes")
    if not isinstance(causes, list):
        raise ValueError(  # noqa: TRY004 - convención del proyecto: ValueError para toda validación de input
            "likely_causes debe ser una lista (puede estar vacía)"
        )
    for index, cause in enumerate(causes):
        missing = [field for field in _REQUIRED_CAUSE_FIELDS if not cause.get(field)]
        if missing:
            raise ValueError(f"likely_causes[{index}]: faltan campos {', '.join(missing)}")
        if cause["confidence"] not in _VALID_CONFIDENCES:
            raise ValueError(
                f"likely_causes[{index}]: confidence inválida {cause['confidence']!r}, "
                f"debe ser una de {sorted(_VALID_CONFIDENCES)}"
            )


def _get_repo_access() -> tuple[repo_access.RepoAccess | None, str | None]:
    try:
        return repo_access.get_frontend_repo(Path.cwd() / "qa-project.yaml"), None
    except repo_access.RepoAccessError as exc:
        return None, str(exc)


def _render_cause(cause: dict[str, object]) -> str:
    location = f"{cause['file']}:{cause['line']}" if cause.get("file") else "(hipótesis conceptual, sin repo real)"
    lines = [f"- **[{cause['confidence']}] {location}**: {cause['reasoning']}"]
    if cause.get("suggested_direction"):
        lines.append(f"  Revisar: {cause['suggested_direction']}")
    return "\n".join(lines)


class BugExplorerAgent:
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
            except Exception as exc:  # noqa: BLE001 - una falla acá cae a razonar solo con la descripción
                repo_error = f"tool-calling falló: {exc}"
                raw = provider.complete(system=_SYSTEM_PROMPT, messages=[{"role": "user", "content": intake.text}])
        else:
            raw = provider.complete(system=_SYSTEM_PROMPT, messages=[{"role": "user", "content": intake.text}])

        payload = json.loads(extract_json(raw, dict))
        _validate(payload)

        causes = payload["likely_causes"]
        if causes:
            content = f"{len(causes)} causa(s) probable(s):\n" + "\n".join(_render_cause(c) for c in causes)
        else:
            content = "Sin causas identificadas — no se pudo trazar el bug con la información disponible."

        pending = list(payload.get("pending_items") or [])
        if repo_error:
            pending.append(f"No se pudo usar el repo de frontend ({repo_error}), causas sin confirmar contra código real.")
        if pending:
            content += "\n\n## Pendiente\n" + "\n".join(f"- {item}" for item in pending)

        return AgentResult(agent="bug_explorer", content=content)


AGENT_REGISTRY["bug_explorer"] = BugExplorerAgent()
