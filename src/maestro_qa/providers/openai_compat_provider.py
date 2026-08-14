import json

import openai

from .base import Tool, ToolExecutor
from .retry import with_retries

_TRANSIENT = (
    openai.RateLimitError,
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.InternalServerError,
)

_MAX_TOOL_ITERATIONS = 8


def _to_openai_tools(tools: list[Tool]) -> list[dict[str, object]]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["parameters"],
            },
        }
        for tool in tools
    ]


class OpenAICompatProvider:
    def __init__(self, model: str, api_key: str, base_url: str | None = None) -> None:
        self._model = model
        self._client = openai.OpenAI(api_key=api_key, base_url=base_url)

    def complete(
        self,
        system: str,
        messages: list[dict[str, object]],
        *,
        tools: list[Tool] | None = None,
        tool_executor: ToolExecutor | None = None,
        **kwargs: object,
    ) -> str:
        conversation: list[dict[str, object]] = [{"role": "system", "content": system}, *messages]

        def call() -> openai.types.chat.ChatCompletionMessage:
            response = self._client.chat.completions.create(  # type: ignore[call-overload]
                model=self._model,
                messages=conversation,
                **({"tools": _to_openai_tools(tools)} if tools else {}),
                **kwargs,
            )
            return response.choices[0].message  # type: ignore[no-any-return]

        for _ in range(_MAX_TOOL_ITERATIONS):
            message = with_retries(call, is_transient=lambda exc: isinstance(exc, _TRANSIENT))

            # Maestro QA solo declara tools de tipo "function" (ver _to_openai_tools), así
            # que nunca deberíamos recibir un custom tool call de vuelta — igual se filtra
            # por las dudas en vez de asumirlo.
            calls = [(tc.id, fn) for tc in (message.tool_calls or []) if (fn := getattr(tc, "function", None))]
            if not calls or not tool_executor:
                return message.content or ""

            conversation.append(
                {
                    "role": "assistant",
                    "content": message.content,
                    "tool_calls": [
                        {"id": call_id, "type": "function", "function": {"name": fn.name, "arguments": fn.arguments}}
                        for call_id, fn in calls
                    ],
                }
            )
            for call_id, fn in calls:
                result = tool_executor(fn.name, json.loads(fn.arguments))
                conversation.append({"role": "tool", "tool_call_id": call_id, "content": result})

        return message.content or ""
