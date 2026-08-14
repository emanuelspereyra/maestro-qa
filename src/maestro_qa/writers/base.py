from dataclasses import dataclass
from typing import Protocol


@dataclass
class WorkItem:
    external_ref: str  # case_id u otro identificador de origen, para trazabilidad/logs
    title: str
    description: str  # HTML — cada backend lo adapta a su propio formato si hace falta


@dataclass
class WriteResult:
    external_id: str
    url: str


class WriterError(Exception):
    pass


class Writer(Protocol):
    def create(self, item: WorkItem) -> WriteResult: ...
