from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Connector(ABC):
    name: str = "base"
    label: str = "Base"
    description: str = ""

    @abstractmethod
    def is_available(self) -> bool:
        ...

    @abstractmethod
    def status(self) -> dict[str, Any]:
        ...

    @abstractmethod
    def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        ...

    def setup_docs(self) -> str:
        return self.description
