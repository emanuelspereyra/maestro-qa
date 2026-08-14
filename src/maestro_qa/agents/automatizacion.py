import ast
import json
from pathlib import Path

from .. import pr_writer, repo_access
from ..json_extraction import extract_json
from ..orchestrator import AgentResult, Intake
from ..providers import Provider
from .registry import AGENT_REGISTRY

_SYSTEM_PROMPT = """Sos un agente de QA que genera automatización frontend en Playwright \
Python con Page Object Model, a partir de la descripción de un ticket o feature.

Reglas obligatorias:
- El Page Object es una subclase de `BasePage` (importada como \
`from pages.base_page import BasePage`), que ya expone `self.page` y `self.base_url`.
- El test usa pytest y las fixtures `base_url` y `qa_target_environment` (ya existen en el \
proyecto vía conftest.py) — nunca hardcodear URLs ni ambientes.
- Locators por rol, label, placeholder o test id. Nunca XPath/CSS frágil sin justificar.
- Web-first assertions de Playwright (`expect(locator).to_be_visible()`, etc.), nunca \
`time.sleep`.
- Si falta una URL, selector, dato o contrato para escribir el código real, NO lo inventes: \
agregalo a `pending_items` y dejá ese punto del código con un comentario `# TODO:` claro.
- Si el mensaje incluye una sección "Casos de prueba ya generados", el test que escribas \
tiene que automatizar EXACTAMENTE los `steps` de los casos con layer "frontend" y \
execution_type "automated" o "both" — no un flujo distinto inventado del ticket.

Devolvé EXCLUSIVAMENTE un objeto JSON (sin texto adicional, sin markdown) con estos campos:
{
  "page_object_filename": "pages/<feature>_page.py",
  "page_object_code": "<código Python completo del Page Object>",
  "test_filename": "tests/test_<feature>.py",
  "test_code": "<código Python completo del test>",
  "pending_items": ["<lista de puntos pendientes, puede estar vacía>"]
}
"""

_REPO_ACCESS_SUFFIX = """

Además, tenés acceso al código real del repo de frontend vía las herramientas \
`list_files`/`read_file`/`write_file`. Explorá el repo para encontrar selectores \
existentes antes de escribir el test. Si un elemento relevante no tiene un selector \
estable, agregale un atributo `data-testid="id-testautomation-<slug>"` con `write_file` \
en el componente real, en vez de dejarlo como pendiente."""


_REQUIRED_FIELDS = ["page_object_filename", "page_object_code", "test_filename", "test_code"]


def _check_syntax(filename: str, code: object) -> None:
    if not isinstance(code, str):
        raise ValueError(f"{filename}: se esperaba código como string, se recibió {type(code).__name__}")  # noqa: TRY004 - convención del proyecto: ValueError para toda validación de input
    try:
        ast.parse(code)
    except SyntaxError as exc:
        raise ValueError(f"{filename}: código Python inválido ({exc})") from exc


def _validate(payload: dict[str, object]) -> None:
    missing = [field for field in _REQUIRED_FIELDS if not payload.get(field)]
    if missing:
        raise ValueError(f"Respuesta incompleta del agente de automatización, faltan campos: {', '.join(missing)}")


def _feature_slug(filename: str) -> str:
    return Path(filename).stem.replace("_", "-")


def _get_repo_access() -> tuple[repo_access.RepoAccess | None, str | None]:
    try:
        return repo_access.get_frontend_repo(Path.cwd() / "qa-project.yaml"), None
    except repo_access.RepoAccessError as exc:
        return None, str(exc)


class AutomatizacionAgent:
    def run(self, intake: Intake, provider: Provider) -> AgentResult:
        repo, repo_error = _get_repo_access()

        if repo is not None:
            try:
                raw = provider.complete(
                    system=_SYSTEM_PROMPT + _REPO_ACCESS_SUFFIX,
                    messages=[{"role": "user", "content": intake.text}],
                    tools=repo_access.TOOLS,
                    tool_executor=repo.execute,
                )
            except Exception as exc:  # noqa: BLE001 - spec 023: cualquier falla acá cae a generar a ciegas
                repo_error = f"tool-calling falló: {exc}"
                repo = None
                raw = provider.complete(system=_SYSTEM_PROMPT, messages=[{"role": "user", "content": intake.text}])
        else:
            raw = provider.complete(system=_SYSTEM_PROMPT, messages=[{"role": "user", "content": intake.text}])

        payload = json.loads(extract_json(raw, dict))
        _validate(payload)

        _check_syntax(payload["page_object_filename"], payload["page_object_code"])
        _check_syntax(payload["test_filename"], payload["test_code"])

        commit: tuple[str, str] | None = None
        commit_error: str | None = None
        if repo is not None:
            try:
                commit = repo.commit_changes(_feature_slug(str(payload["page_object_filename"])))
            except RuntimeError as exc:
                commit_error = str(exc)

        sections = [
            f"## {payload['page_object_filename']}\n```python\n{payload['page_object_code']}\n```",
            f"## {payload['test_filename']}\n```python\n{payload['test_code']}\n```",
        ]
        pending = list(payload.get("pending_items") or [])
        if repo_error:
            pending.append(f"No se pudo usar el repo de frontend ({repo_error}), generado sin ese contexto.")
        if commit_error:
            pending.append(f"Se exploró el repo de frontend pero no se pudo comitear los cambios ({commit_error}).")
        if pending:
            sections.append("## Pendiente\n" + "\n".join(f"- {item}" for item in pending))

        if commit is not None and repo is not None:
            branch, sha = commit
            sections.append(
                "## Cambios en el repo de frontend\n"
                f"- Rama: `{branch}` (commit `{sha[:8]}`)\n"
                f"- Path local: `{repo.path}`\n"
                f"- Archivos: {', '.join(sorted(repo.touched_files))}\n"
                "- No se pusheó ni se abrió PR — revisar y subir a mano."
            )

        feature_slug = _feature_slug(str(payload["page_object_filename"]))
        publish = pr_writer.publish_generated_code(
            qa_project_path=Path.cwd() / "qa-project.yaml",
            feature_slug=feature_slug,
            files={
                str(payload["page_object_filename"]): str(payload["page_object_code"]),
                str(payload["test_filename"]): str(payload["test_code"]),
            },
            pr_title=f"test(automatizacion): {feature_slug}",
            pr_body="Generado por Maestro QA a partir de un ticket. Revisar antes de mergear.",
        )
        if publish is not None:
            lines = ["## Repo de automatización"]
            if publish.branch:
                lines.append(f"- Rama: `{publish.branch}` (commit `{(publish.commit_sha or '')[:8]}`)")
            lines.append(f"- Pusheada: {'sí' if publish.pushed else 'no'}")
            if publish.pr_url:
                lines.append(f"- PR: {publish.pr_url}")
            if publish.error:
                lines.append(f"- {publish.error}")
            sections.append("\n".join(lines))

        return AgentResult(agent="automatizacion", content="\n\n".join(sections))


AGENT_REGISTRY["automatizacion"] = AutomatizacionAgent()
