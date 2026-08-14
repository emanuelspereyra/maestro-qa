import anthropic

from .base import Tool, ToolExecutor
from .retry import with_retries

_TRANSIENT = (
    anthropic.RateLimitError,
    anthropic.APITimeoutError,
    anthropic.APIConnectionError,
    anthropic.InternalServerError,
)

_MAX_TOOL_ITERATIONS = 8


def _to_anthropic_tools(tools: list[Tool]) -> list[dict[str, object]]:
    return [
        {"name": tool["name"], "description": tool["description"], "input_schema": tool["parameters"]}
        for tool in tools
    ]


class AnthropicProvider:
    def __init__(self, model: str, api_key: str) -> None:
        self._model = model
        self._client = anthropic.Anthropic(api_key=api_key)

    def complete(
        self,
        system: str,
        messages: list[dict[str, object]],
        *,
        tools: list[Tool] | None = None,
        tool_executor: ToolExecutor | None = None,
        **kwargs: object,
    ) -> str:
        max_tokens = kwargs.pop("max_tokens", 4096)
        conversation = list(messages)

        def call() -> anthropic.types.Message:
            return self._client.messages.create(  # type: ignore[call-overload,no-any-return]
                model=self._model,
                system=system,
                messages=conversation,
                max_tokens=max_tokens,
                **({"tools": _to_anthropic_tools(tools)} if tools else {}),
                **kwargs,
            )

        for _ in range(_MAX_TOOL_ITERATIONS):
            response = with_retries(call, is_transient=lambda exc: isinstance(exc, _TRANSIENT))

            if response.stop_reason != "tool_use" or not tool_executor:
                return "".join(block.text for block in response.content if block.type == "text")

            conversation.append({"role": "assistant", "content": response.content})
            tool_results = [
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": tool_executor(block.name, dict(block.input)),
                }
                for block in response.content
                if block.type == "tool_use"
            ]
            conversation.append({"role": "user", "content": tool_results})

        return "".join(block.text for block in response.content if block.type == "text")
