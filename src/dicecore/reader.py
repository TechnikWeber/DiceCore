"""
The thing that actually reads a roll: capture → settle → engine → result.

One object, held by both the CLI and the server, so there is exactly one place where the
camera is open and exactly one place where a mode change takes effect. A dice tower has one
camera; two half-initialised readers fighting over `/dev/video0` is a bug that only shows up
once the UI has more than one tab open.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from .capture import CaptureError, FrameSource, PushSource, open_source
from .capture.settle import wait_for_settle
from .config import Settings
from .dice import Frame, RollResult
from .engine import Engine, EngineError, build_engine


class Reader:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.push = PushSource()
        self._lock = threading.RLock()
        self._source: FrameSource | None = None
        self._engine: Engine | None = None
        self._last: RollResult | None = None
        self._last_jpeg: bytes | None = None
        self._last_frame: Frame | None = None
        #: Why the source or engine is unavailable, in words the UI can show.
        self.problems: list[str] = []

    # --- lazy, replaceable parts --------------------------------------------
    def source(self) -> FrameSource:
        with self._lock:
            if self._source is None:
                self._source = open_source(self.settings, self.push)
            return self._source

    def engine(self) -> Engine:
        with self._lock:
            if self._engine is None:
                self._engine = build_engine(self.settings)
            return self._engine

    def reload(self, settings: Settings | None = None) -> None:
        """Apply changed settings. Closes the camera, so it is not free — call it on save."""
        with self._lock:
            if settings is not None:
                self.settings = settings
            if self._source is not None:
                try:
                    self._source.close()
                except Exception:
                    pass
            self._source = None
            self._engine = None
            self.problems = []

    def close(self) -> None:
        with self._lock:
            if self._source is not None:
                self._source.close()
            self._source = None
            self._engine = None

    # --- reading ------------------------------------------------------------
    def read(self, wait_for_still: bool = True) -> RollResult:
        """
        Read one roll.

        Raises `CaptureError` / `EngineError` with a message meant for a human — the UI
        prints them verbatim, because "no camera bound to dtoverlay=imx519" is a repair
        instruction and "read failed" is not.
        """
        with self._lock:
            source = self.source()
            engine = self.engine()
            settle = self.settings.settle

            warnings: list[str] = []
            if wait_for_still and settle.enabled and self.settings.capture.source != "folder":
                outcome = wait_for_settle(source.grab, settle)
                frame = outcome.frame
                if outcome.warning:
                    warnings.append(outcome.warning)
            else:
                frame = source.grab()

            result = engine.read(frame)
            result.warnings = warnings + result.warnings
            self._last = result
            self._last_frame = frame
            self._last_jpeg = None
            return result

    def read_image(self, image: Any, source_name: str = "upload") -> RollResult:
        """Read a frame that came from outside — an upload, or a push from an agent."""
        with self._lock:
            frame = Frame(image=image, source=source_name)
            result = self.engine().read(frame)
            self._last = result
            self._last_frame = frame
            self._last_jpeg = None
            return result

    # --- what the UI needs afterwards ---------------------------------------
    @property
    def last(self) -> RollResult | None:
        return self._last

    def last_jpeg(self) -> bytes | None:
        """The frame the last result came from, encoded once and cached."""
        with self._lock:
            if self._last_jpeg is not None:
                return self._last_jpeg
            frame = self._last_frame
            if frame is None:
                return None
            if frame.jpeg:
                self._last_jpeg = frame.jpeg
                return self._last_jpeg
            if frame.image is None:
                return None
            try:
                import cv2
            except ImportError:
                return None
            ok, buf = cv2.imencode(
                ".jpg", frame.image,
                [int(cv2.IMWRITE_JPEG_QUALITY), self.settings.capture.jpeg_quality],
            )
            self._last_jpeg = buf.tobytes() if ok else None
            return self._last_jpeg

    def preview_jpeg(self) -> bytes:
        """A fresh frame for the live view, without running the engine over it."""
        with self._lock:
            frame = self.source().grab()
            self._last_frame = frame
            self._last_jpeg = None
            jpeg = self.last_jpeg()
            if jpeg is None:
                raise CaptureError("Could not encode a preview frame (is OpenCV installed?).")
            return jpeg

    def status(self) -> dict[str, Any]:
        """Everything the overview panel shows, with failures as text rather than as 500s."""
        with self._lock:
            out: dict[str, Any] = {
                "at": time.time(),
                "capture": {"configured": self.settings.capture.source},
                "engine": {"configured": self.settings.engine.mode},
                "problems": [],
            }
            try:
                out["capture"].update(self.source().describe())
            except (CaptureError, Exception) as exc:
                out["problems"].append(str(exc))
            try:
                out["engine"].update(self.engine().describe())
            except (EngineError, Exception) as exc:
                out["problems"].append(str(exc))
            out["last"] = self._last.to_json() if self._last else None
            return out
