from collections.abc import Callable
from typing import Protocol

# Formato provider-agnóstico: cada Provider lo traduce a lo que su SDK espera
# (input_schema de Anthropic, function.parameters de OpenAI-compat).
Tool = dict[str, object]
ToolExecutor = Callable[[str, dict[str, object]], str]


class Provider(Protocol):
    def complete(
        self,
        system: str,
        messages: list[dict[str, object]],
        *,
        tools: list[Tool] | None = None,
        tool_executor: ToolExecutor | None = None,
        **kwargs: object,
    ) -> str: ...
