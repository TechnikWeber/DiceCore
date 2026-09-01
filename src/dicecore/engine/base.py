"""The engine interface: a frame in, a RollResult out."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..dice import Frame, RollResult


class EngineError(RuntimeError):
    """The engine cannot run at all (missing model, unreachable peer, no OpenCV)."""


class Engine(ABC):
    name = "base"

    @abstractmethod
    def read(self, frame: Frame) -> RollResult:
        """Recognise the dice in one settled frame."""

    def close(self) -> None:
        """Release whatever the engine holds. Safe to call twice."""

    def describe(self) -> dict[str, Any]:
        return {"name": self.name}
