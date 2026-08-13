from typing import Protocol


class Provider(Protocol):
    def complete(self, system: str, messages: list[dict[str, str]], **kwargs: object) -> str: ...
