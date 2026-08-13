from typing import TYPE_CHECKING, Protocol

from ..providers import Provider

if TYPE_CHECKING:
    from ..orchestrator import AgentResult, Intake


class Agent(Protocol):
    def run(self, intake: "Intake", provider: Provider) -> "AgentResult": ...


AGENT_REGISTRY: dict[str, Agent] = {}
