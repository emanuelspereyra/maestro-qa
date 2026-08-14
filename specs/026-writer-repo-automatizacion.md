# 026 — Writer hacia repo de automatización: push + PR (CDA-60)

## Problema
`automatizacion`/`automatizacion_api` generan Page Object+test o cliente API+test, pero
hoy eso queda solo como texto en el resultado — alguien tiene que copiarlo a mano al repo
real. Spec 023 le dio a `automatizacion` acceso de lectura/escritura al repo de
**frontend** (para agregar un `data-testid` faltante), pero deliberadamente nunca pushea
ni abre PR. CDA-60 es el paso que falta: llevar el código YA generado a un repo real, con
push y PR de verdad — decisión explícita de Emanuel en su momento de frenarlo hasta tener
esto bien pensado.

## Alcance
Dos decisiones de diseño de Emanuel antes de implementar:
- **Repo destino**: uno separado, `repositories.automation` en `qa-project.yaml` (mismo
  layout que el bundle vendorizado ya anticipaba con su carpeta `qa-automation` — no el
  mismo repo de frontend/backend que spec 023 explora).
- **Nivel de automatismo**: push + PR automático en cada corrida que genera código nuevo,
  **nunca auto-merge** — el merge lo hace siempre una persona.

Cubre `automatizacion` (frontend) y `automatizacion_api` (backend) por igual, con la
misma función compartida — no se duplica la lógica de push/PR en cada agente.

**Fuera de esta spec:**
- Auto-merge — explícitamente nunca, no es negociable en esta spec.
- Soporte de PR para providers que no sean GitHub (GitLab/Bitbucket/Azure DevOps) — se
  pushea la rama igual, pero abrir el PR queda como pendiente manual con una nota clara.
  `verify_repository.py` (spec 009) ya detecta el provider; se reusa esa detección.
- Reintentar el push si falla por conflicto (rama ya existe en el remoto con otro
  contenido) — se reporta como pendiente, no se resuelve solo.
- Aplicar el mismo patrón a `calidad_codigo` — no genera código, no aplica.

## Diseño

### `qa-project.yaml`: nuevo repo `automation`
Mismo shape que `frontend`/`backend` (`url`, `branch`). `onboarding.ensure_project()`
ahora también lo verifica (de solo lectura, con `_verify_repo`, igual que los otros dos)
si está configurado.

### `repo_access.get_repo()` generalizada
`get_frontend_repo()` se generaliza a `get_repo(qa_project_path, repo_key="frontend")` —
mismo comportamiento exacto para "frontend" (default, sin romper nada de spec 023), y
reusable para `repo_key="automation"`. `get_frontend_repo()` queda como wrapper fino para
no tocar los call sites existentes (`automatizacion.py`, `calidad_codigo.py`).

### Módulo nuevo: `pr_writer.py`
```python
def push_branch(repo: RepoAccess, branch: str, token: str) -> None
def open_pull_request(repo_url: str, token: str, branch: str, base: str, title: str, body: str) -> str  # devuelve pr_url
def publish_generated_code(qa_project_path, feature_slug, files: dict[str, str], pr_title: str, pr_body: str) -> PublishResult | None
```
`publish_generated_code` es la función que llaman `automatizacion.py`/`automatizacion_api.py`
— centraliza TODO el flujo (clonar, escribir, comitear, pushear, abrir PR) en un solo
lugar para no duplicarlo en los dos agentes. Devuelve `None` si `repositories.automation`
no está configurado (comportamiento actual, sin cambios). Si está configurado, nunca
levanta una excepción — cualquier falla queda en `PublishResult.error`, y el código ya
generado se sigue devolviendo igual (mismo criterio de resiliencia que specs 023/024: un
problema de infraestructura de repo nunca tira abajo el resultado útil que ya se generó).

**Token nunca en la URL ni en `.git/config` persistido**: el push usa
`git -c http.extraHeader="Authorization: Bearer <token>" push origin <branch>` — el header
solo vive para esa invocación puntual del subproceso, no se guarda en ningún lado.

**PR solo si el provider es GitHub** (detectado igual que `verify_repository.py`) — usa la
API REST de GitHub (`POST /repos/{owner}/{repo}/pulls`) vía `httpx` (ya es dependencia).
Con cualquier otro provider, se pushea la rama igual y se reporta en `pending_items` que
hay que abrir el PR a mano.

### Credenciales
`MAESTRO_GITHUB_TOKEN` (ya estaba en `.env.example`, sin usar hasta ahora) — sin él no se
puede pushear (hace falta autenticación de escritura). Si falta: se comitea local
únicamente (mismo comportamiento que `repositories.frontend` en spec 023) y se reporta en
`pending_items` que falta `MAESTRO_GITHUB_TOKEN` para completar el push+PR.

### Flujo en `automatizacion.py`/`automatizacion_api.py`
Después de validar el payload generado (ya existe), un paso nuevo:
```python
publish = pr_writer.publish_generated_code(
    qa_project_path=Path.cwd() / "qa-project.yaml",
    feature_slug=_feature_slug(payload["page_object_filename"]),  # o el de API
    files={payload["page_object_filename"]: payload["page_object_code"], payload["test_filename"]: payload["test_code"]},
    pr_title=f"test(automatizacion): {feature_slug}",
    pr_body="Generado por Maestro QA a partir de un ticket. Revisar antes de mergear.",
)
```
Si `publish is not None`: se agrega una sección `## Repo de automatización` con la rama,
el commit, si se pusheó, y la URL del PR si se abrió — o el motivo si algo de eso falló.

## Criterios de aceptación
- Sin `repositories.automation` configurado: comportamiento idéntico al actual (sin
  sección nueva en el resultado).
- Con un repo local real (bare, como "remoto" para simular push de verdad) y
  `MAESTRO_GITHUB_TOKEN` seteado: el push llega al remoto de verdad (verificable con
  `git log` en el bare repo) — probado sin mockear git.
- La apertura de PR se prueba con la llamada HTTP a la API de GitHub mockeada (no hay
  forma de probarla contra GitHub real sin credenciales) — se verifica el payload
  enviado (owner/repo/branch/base/title/body) y el manejo de errores (401, 404,
  ya existe un PR abierto para esa rama).
- Sin `MAESTRO_GITHUB_TOKEN`: cae a comit local únicamente, con nota clara en
  `pending_items`.
- Un provider no-GitHub: pushea igual, reporta que el PR hay que abrirlo a mano.
- Nunca auto-merge — no existe ningún código que llame a un endpoint de merge.
- Cualquier falla (push rechazado, token inválido, repo no encontrado) nunca rompe la
  corrida completa — el código generado se sigue devolviendo.
- Suite completa (`ruff`, `mypy`, `pytest`) en verde.

## Fuera de alcance / backlog
- Soporte de PR para GitLab/Bitbucket/Azure DevOps.
- Reintentos/resolución de conflictos de push.
- Validar contra un GitHub real (necesita un repo de prueba + token real) — mismo caveat
  que SonarQube efímero y el tool-calling de providers OpenAI-compat: no probado en este
  entorno, queda para probar a mano cuando haya credenciales.
