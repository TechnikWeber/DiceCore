"""
Everything that tells a person what is going on: the screen, the lamps, the buzzer.

The hub owns a thread. Not for speed — an SPI panel takes tens of milliseconds per frame,
and a buzzer pattern is a tenth of a second of deliberate sleeping. Doing either on the
thread that reads the dice would put the decoration in front of the number, which is exactly
backwards.
"""

from __future__ import annotations

import queue
import threading
from typing import Any

from ..config import OutputSettings
from .base import OutputDevice, OutputError
from .displays import PANELS, DisplayOutput
from .signals import SignalOutput
from .state import (
    ERROR,
    IDLE,
    READING,
    READY,
    RESULT,
    ROLLING,
    VOID,
    Presentation,
    presentation_for,
)

__all__ = [
    "OutputHub", "OutputDevice", "OutputError", "Presentation", "presentation_for",
    "PANELS", "IDLE", "ROLLING", "READING", "RESULT", "READY", "VOID", "ERROR",
]


class OutputHub:
    """Fans one `Presentation` out to every enabled output, on its own thread."""

    def __init__(self, settings: OutputSettings) -> None:
        self.settings = settings
        self.display: DisplayOutput | None = None
        self.signals: SignalOutput | None = None
        self.problems: list[str] = []

        if settings.display.enabled:
            try:
                self.display = DisplayOutput(settings.display)
            except OutputError as exc:
                self.problems.append(str(exc))
        if settings.signals.enabled:
            try:
                self.signals = SignalOutput(settings.signals)
            except OutputError as exc:
                self.problems.append(str(exc))

        self.latest = Presentation()
        self._queue: queue.Queue[Presentation | None] = queue.Queue(maxsize=4)
        self._worker: threading.Thread | None = None
        if self.devices:
            self._worker = threading.Thread(target=self._run, name="dicecore-output",
                                            daemon=True)
            self._worker.start()
            self.update(Presentation(IDLE))

    @property
    def devices(self) -> list[OutputDevice]:
        return [d for d in (self.display, self.signals) if d is not None]

    @property
    def enabled(self) -> bool:
        return bool(self.devices)

    # --- input --------------------------------------------------------------
    def update(self, presentation: Presentation) -> None:
        """
        Show this. Never blocks the caller.

        A full queue means the outputs are behind, and the newest state is the only one that
        matters — so the oldest is dropped rather than the newest, and rather than making the
        dice wait for a screen.
        """
        self.latest = presentation
        if not self.devices:
            return
        try:
            self._queue.put_nowait(presentation)
        except queue.Full:
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(presentation)
            except (queue.Empty, queue.Full):
                pass

    # --- output -------------------------------------------------------------
    def _run(self) -> None:
        while True:
            presentation = self._queue.get()
            if presentation is None:
                return
            try:
                self._present(presentation)
            except Exception as exc:  # a broken screen must never take the reader with it
                self.problems.append(str(exc))

    def _present(self, presentation: Presentation) -> None:
        for device in self.devices:
            device.present(presentation)
        if not (presentation.celebrate or presentation.lament):
            return
        if presentation.phase not in (RESULT, READY, VOID):
            return
        # The flourish. Interrupted the moment anything newer arrives, because a new roll
        # matters more than finishing an animation about the last one.
        import time

        frames = max(1, self.settings.animation_frames)
        for step in range(1, frames + 1):
            if not self._queue.empty():
                return
            frame = Presentation(**{**presentation.__dict__, "anim": step})
            for device in self.devices:
                if device.animates:
                    device.present(frame)
            time.sleep(self.settings.animation_interval_s)
        for device in self.devices:
            device.present(presentation)

    def close(self) -> None:
        if self._worker is not None:
            self._queue.put(None)
            self._worker.join(timeout=2.0)
            self._worker = None
        for device in self.devices:
            device.close()

    def describe(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "display": self.display.describe() if self.display else None,
            "signals": self.signals.describe() if self.signals else None,
            "state": self.latest.to_json(),
            "problems": self.problems[-5:],
        }
