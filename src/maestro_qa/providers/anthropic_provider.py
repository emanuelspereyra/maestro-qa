import anthropic

from .retry import with_retries

_TRANSIENT = (
    anthropic.RateLimitError,
    anthropic.APITimeoutError,
    anthropic.APIConnectionError,
    anthropic.InternalServerError,
)


class AnthropicProvider:
    def __init__(self, model: str, api_key: str) -> None:
        self._model = model
        self._client = anthropic.Anthropic(api_key=api_key)

    def complete(self, system: str, messages: list[dict[str, str]], **kwargs: object) -> str:
        max_tokens = kwargs.pop("max_tokens", 4096)

        def call() -> str:
            response = self._client.messages.create(  # type: ignore[call-overload]
                model=self._model,
                system=system,
                messages=messages,
                max_tokens=max_tokens,
                **kwargs,
            )
            return "".join(block.text for block in response.content if block.type == "text")

        return with_retries(call, is_transient=lambda exc: isinstance(exc, _TRANSIENT))
