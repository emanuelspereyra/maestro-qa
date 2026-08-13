# 001 — Motor core: adaptador multi-LLM

## Problema
Cada agente especializado (casos manuales, automatización, etc.) necesita llamar a un LLM
para generar su output. CDA quiere poder elegir qué proveedor usa (Anthropic, OpenAI,
Gemini, Kimi/Moonshot, Qwen, DeepSeek) sin que eso implique reescribir la lógica de cada
agente. Sin esta capa, cada agente termina atado a un proveedor específico.

## Alcance
Cubre las tareas CDA-11, CDA-12, CDA-13 (epic "Motor core"):
- Interfaz común de "provider" que cualquier agente puede llamar para obtener texto.
- Dos implementaciones concretas que cubren los 6 proveedores pedidos.
- Config de qué proveedor/modelo/credencial usar, leída de variables de entorno.
- Retries con backoff ante errores transitorios (rate limit, 5xx, timeout).

**Fuera de esta spec:** la lógica de cada agente especializado (tiene su propia spec por
agente), streaming de respuesta, tool-calling del lado del LLM, embeddings, y selección de
proveedor distinta por agente (ver Backlog).

## Diseño

**Por qué solo 2 implementaciones y no 6:** de los 6 proveedores pedidos, 5 exponen una API
compatible con el formato Chat Completions de OpenAI (OpenAI, Gemini, Kimi/Moonshot, Qwen,
DeepSeek) — alcanza con un único adaptador que apunta a distinto `base_url` según el
proveedor. Anthropic usa su propia Messages API y necesita su propio adaptador. Reimplementar
un cliente por proveedor sería repetir el mismo código 6 veces para lo que en la práctica son
2 formatos de API.

**Interfaz común** (`providers/base.py`):
```python
class Provider(Protocol):
    def complete(self, system: str, messages: list[dict[str, str]], **kwargs) -> str: ...
```
Solo texto in/texto out — es lo único que necesita cualquiera de los 10 agentes especializados
hoy.

**Implementaciones:**
- `providers/anthropic_provider.py` — usa el SDK `anthropic`, llama a Messages API.
- `providers/openai_compat_provider.py` — usa el SDK `openai` con `base_url` configurable;
  cubre OpenAI, Gemini (endpoint compatible), Kimi, Qwen, DeepSeek con la misma clase,
  cambiando solo `base_url` y `api_key`.

**Config** (`providers/config.py`): lee de variables de entorno —
`MAESTRO_PROVIDER` (uno de: `anthropic`, `openai`, `gemini`, `kimi`, `qwen`, `deepseek`),
`MAESTRO_MODEL`, `MAESTRO_API_KEY`. Una función `get_provider() -> Provider` instancia la
implementación correcta según `MAESTRO_PROVIDER`. Un solo proveedor para todo el motor en v1
— no hay override por agente (ver Backlog).

**Retries** (`providers/retry.py`): wrapper que reintenta `complete()` ante errores
transitorios (rate limit, 5xx, timeout de red) con backoff exponencial, tope de 3 intentos.
Agota reintentos → levanta `ProviderError` con la causa original. Errores no transitorios
(401, 400 de validación) no reintentan, se propagan directo.

## Criterios de aceptación
- `get_provider()` devuelve una instancia funcional según `MAESTRO_PROVIDER` sin tocar código.
- Las dos implementaciones cumplen el mismo `Protocol` — un agente puede recibir cualquiera
  de las dos sin saber cuál es.
- Un error transitorio simulado dispara reintentos y termina en éxito o en `ProviderError`
  tras 3 intentos.
- Cambiar de proveedor (ej. de Anthropic a DeepSeek) es cambiar 2-3 variables de entorno,
  cero cambios de código en los agentes.

## Fuera de alcance / backlog
- **Proveedor distinto por agente** (ej. DeepSeek para generación de datos, Claude para
  triage de bugs) — útil como optimización de costo/calidad más adelante, pero v1 asume un
  solo proveedor para todo el motor. Cuando se pida, se resuelve extendiendo `config.py` con
  un mapa `agente -> proveedor` sin tocar la interfaz `Provider`.
- **Streaming y tool-calling** — ningún agente de v1 los necesita.
- **Embeddings / búsqueda semántica** — no hay agente que lo requiera todavía (podría
  aparecer si se agrega un agente de trazabilidad más sofisticado).
