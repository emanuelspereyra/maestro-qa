import os

from .anthropic_provider import AnthropicProvider
from .base import Provider
from .openai_compat_provider import OpenAICompatProvider

# ponytail: endpoints internacionales por defecto; Qwen/Kimi tienen dominios .cn
# separados para cuentas registradas en China — ajustar si CDA usa esas cuentas.
_OPENAI_COMPAT_BASE_URLS = {
    "openai": None,
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "kimi": "https://api.moonshot.ai/v1",
    "qwen": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    "deepseek": "https://api.deepseek.com/v1",
}


_REQUIRED_ENV_VARS = ("MAESTRO_PROVIDER", "MAESTRO_MODEL", "MAESTRO_API_KEY")


def get_provider() -> Provider:
    missing = [var for var in _REQUIRED_ENV_VARS if not os.environ.get(var)]
    if missing:
        raise ValueError(
            f"Faltan variables de entorno: {', '.join(missing)}. "
            "Copiá .env.example a .env y completalas (ver README)."
        )
    name = os.environ["MAESTRO_PROVIDER"]
    model = os.environ["MAESTRO_MODEL"]
    api_key = os.environ["MAESTRO_API_KEY"]

    if name == "anthropic":
        return AnthropicProvider(model=model, api_key=api_key)

    if name in _OPENAI_COMPAT_BASE_URLS:
        return OpenAICompatProvider(
            model=model, api_key=api_key, base_url=_OPENAI_COMPAT_BASE_URLS[name]
        )

    raise ValueError(f"Unknown MAESTRO_PROVIDER: {name}")
