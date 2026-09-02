"""
Frames that arrive from outside: a remote agent POSTing to `/api/v1/frame`, or the UI
uploading a photo to try the engine on.

Holds exactly one frame. A dice reader has no use for a backlog — the newest frame is the
only interesting one, and an unbounded queue on a Pi is a memory leak with extra steps.
"""

from __future__ import annotations

import threading
from typing import Any

from ..dice import Frame
from .base import CaptureError, FrameSource


class PushSource(FrameSource):
    name = "push"
    is_live = False

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._frame: Frame | None = None
        self._received = 0

    def offer(self, frame: Frame) -> None:
        with self._lock:
            self._frame = frame
            self._received += 1

    def grab(self) -> Frame:
        with self._lock:
            if self._frame is None:
                raise CaptureError(
                    "No frame has been pushed yet. Point an agent at POST /api/v1/frame, or "
                    "upload an image in the web UI."
                )
            return self._frame

    def describe(self) -> dict[str, Any]:
        return {"name": self.name, "received": self._received, "has_frame": self._frame is not None}
