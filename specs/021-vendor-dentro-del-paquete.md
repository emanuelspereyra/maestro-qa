# 021 — Vendor bundle dentro del paquete instalable

## Problema
Probando `uvx` para el servidor MCP (respuesta a "¿qué pasa si la máquina de otra persona
no tiene nada instalado?") apareció un bug real: `vendor/qa-intelligent-skill-bundle/`
vivía en la raíz del repo, fuera de `src/maestro_qa/`. `pip install -e .` (instalación
editable, la única que usamos hasta ahora en desarrollo) nunca lo notó porque un install
editable no copia nada — `__file__` sigue apuntando al checkout real, con `vendor/` ahí al
lado. Pero `uvx`/cualquier instalación por wheel **construye** el paquete en un directorio
aislado (`~/.cache/uv/...`) copiando solo lo que hatchling empaqueta — y `vendor/` en la
raíz del repo no forma parte de esa build. Resultado real, reproducido: `ensure_project`
falla con `No such file or directory` buscando `init_qa_project.py` dentro del caché de uv.

## Alcance
- Mover `vendor/qa-intelligent-skill-bundle/` de la raíz del repo a
  `src/maestro_qa/vendor/qa-intelligent-skill-bundle/` — dentro del árbol que hatchling ya
  empaqueta (`packages = ["src/maestro_qa"]`), así queda incluido en cualquier instalación
  (editable, wheel, `uvx`, `pipx`) sin configuración extra.
- Actualizar `vendor_bundle.scripts_dir()` para calcular la ruta relativa al propio paquete
  (`Path(__file__).resolve().parent`), no al repo (`parents[2]`).
- Re-verificar con `uvx` real (no solo el cliente MCP crudo) que `ensure_project` y los
  agentes que dependen del bundle (`casos_manuales`, `datos_prueba`) funcionan sin ningún
  install previo en la máquina.

**Fuera de esta spec:** empaquetar y distribuir en PyPI — sigue siendo instalación desde un
path local o un repo git, no un índice público.

## Diseño

**Por qué mover el directorio en vez de agregar `force-include` en hatchling:** las dos
opciones resuelven el síntoma, pero mover el directorio evita mantener dos configuraciones
de build distintas (una para editable, otra para wheel) y dos ubicaciones posibles del
mismo bundle en el árbol de archivos — con el bundle *dentro* del paquete, hatchling lo
incluye por el mismo mecanismo que ya empaqueta todo `src/maestro_qa/`, sin reglas nuevas.

**Cambio en `vendor_bundle.py`:** `_DEFAULT_SCRIPTS_DIR` pasa de
`Path(__file__).resolve().parents[2] / "vendor" / ...` (repo root) a
`Path(__file__).resolve().parent / "vendor" / ...` (dentro del propio paquete). Sigue
siendo un valor por default, no una ruta hardcodeada — `MAESTRO_QA_BUNDLE_SCRIPTS` sigue
pudiendo sobreescribirla si hace falta.

## Criterios de aceptación
- `uvx --from <repo> maestro-qa-mcp` (sin ningún install previo en la máquina) responde
  correctamente a `ensure_project` y a un `run_qa` que dispare `casos_manuales`.
- La suite de tests completa sigue en verde tras el movimiento (los tests usan
  `vendor_bundle.scripts_dir()`, no rutas hardcodeadas al vendor).
- `ruff`/`mypy` siguen excluyendo el bundle vendorizado en su nueva ubicación (el patrón
  `"vendor"` en `extend-exclude`/`exclude` matchea por nombre de carpeta a cualquier
  profundidad, no necesita cambiar).

## Fuera de alcance / backlog
- **Publicar en PyPI** — instalación sigue siendo desde path local o repo git.
