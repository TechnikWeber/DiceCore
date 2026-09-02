"""What an output is: something you can hand a `Presentation` to."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .state import Presentation


class OutputError(RuntimeError):
    """An output cannot be set up. Never fatal — a missing screen must not stop the dice."""


class OutputDevice(ABC):
    name = "device"

    @abstractmethod
    def present(self, presentation: Presentation) -> None:
        """Show this state. Called from the hub's thread, so it may block for a few ms."""

    #: Whether the hub should send animation frames to this device.
    animates = False

    def close(self) -> None:
        """Release pins and buses. Safe to call twice."""

    def describe(self) -> dict[str, Any]:
        return {"name": self.name}
