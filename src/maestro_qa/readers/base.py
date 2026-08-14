from dataclasses import dataclass
from typing import Protocol


@dataclass
class FetchedTicket:
    external_id: str
    title: str
    text: str  # armado y listo para usarse como intake.text


class ReaderError(Exception):
    pass


class Reader(Protocol):
    def fetch(self, external_id: str) -> FetchedTicket: ...
