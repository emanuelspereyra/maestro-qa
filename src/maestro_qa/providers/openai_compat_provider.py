import openai

from .retry import with_retries

_TRANSIENT = (
    openai.RateLimitError,
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.InternalServerError,
)


class OpenAICompatProvider:
    def __init__(self, model: str, api_key: str, base_url: str | None = None) -> None:
        self._model = model
        self._client = openai.OpenAI(api_key=api_key, base_url=base_url)

    def complete(self, system: str, messages: list[dict[str, str]], **kwargs: object) -> str:
        def call() -> str:
            response = self._client.chat.completions.create(  # type: ignore[call-overload]
                model=self._model,
                messages=[{"role": "system", "content": system}, *messages],
                **kwargs,
            )
            return response.choices[0].message.content or ""

        return with_retries(call, is_transient=lambda exc: isinstance(exc, _TRANSIENT))
