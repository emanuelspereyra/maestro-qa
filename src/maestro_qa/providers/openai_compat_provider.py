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

        def call(include_tools: bool) -> openai.types.chat.ChatCompletionMessage:
            response = self._client.chat.completions.create(  # type: ignore[call-overload]
                model=self._model,
                messages=conversation,
                **({"tools": _to_openai_tools(tools)} if include_tools and tools else {}),
                **kwargs,
            )
            return response.choices[0].message  # type: ignore[no-any-return]

        for iteration in range(_MAX_TOOL_ITERATIONS):
            # En la última iteración se corta el acceso a tools para forzar una
            # respuesta de texto final — sin esto, si el modelo sigue pidiendo tool calls
            # al llegar al tope, se devuelve "" y se pierde todo lo explorado/escrito
            # hasta ahí (bug real, auditoría 2026-08-14, mismo fix que AnthropicProvider).
            is_last = iteration == _MAX_TOOL_ITERATIONS - 1

            def call_this_iteration(skip_tools: bool = is_last) -> openai.types.chat.ChatCompletionMessage:
                return call(not skip_tools)

            message = with_retries(call_this_iteration, is_transient=lambda exc: isinstance(exc, _TRANSIENT))

            # Maestro QA solo declara tools de tipo "function" (ver _to_openai_tools), así
            # que nunca deberíamos recibir un custom tool call de vuelta — igual se filtra
            # por las dudas en vez de asumirlo.
            calls = [(tc.id, fn) for tc in (message.tool_calls or []) if (fn := getattr(tc, "function", None))]
            if not calls or not tool_executor or is_last:
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
                try:
                    args = json.loads(fn.arguments)
                except json.JSONDecodeError as exc:
                    result = f"error: argumentos inválidos ({exc})"
                else:
                    result = tool_executor(fn.name, args)
                conversation.append({"role": "tool", "tool_call_id": call_id, "content": result})

        raise AssertionError("unreachable: el loop siempre retorna en la última iteración")
