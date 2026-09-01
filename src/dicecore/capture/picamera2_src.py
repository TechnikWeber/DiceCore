"""
CSI cameras through picamera2, when it is available.

Faster than shelling out per frame, so this is what settle detection wants: it needs a
handful of frames per second to tell a tumbling die from a settled one. Falls back to
`rpicam` when the system package is missing, which is the normal case inside a venv unless
it was created with `--system-site-packages`.
"""

from __future__ import annotations

import time
from typing import Any

from ..dice import Frame
from .base import CaptureError, FrameSource


class Picamera2Source(FrameSource):
    name = "picamera2"

    def __init__(
        self,
        width: int = 1280,
        height: int = 720,
        tuning_file: str = "",
        focus_mode: str = "manual",
        focus_dioptre: float = 0.0,
    ) -> None:
        try:
            from picamera2 import Picamera2
        except ImportError as exc:
            raise CaptureError(
                "picamera2 is not importable. It is a system package: install it with "
                "`sudo apt install python3-picamera2` and create the venv with "
                "--system-site-packages, or use capture.source=rpicam instead."
            ) from exc

        tuning = None
        if tuning_file:
            tuning = Picamera2.load_tuning_file(tuning_file)
        self._cam = Picamera2(tuning=tuning)
        config = self._cam.create_still_configuration(main={"size": (width, height)})
        self._cam.configure(config)
        self._cam.start()
        # AE/AWB need a moment after start or the first frames come out dark, which reads
        # as "the engine cannot find any dice".
        time.sleep(0.5)
        self._apply_focus(focus_mode, focus_dioptre)
        self.width, self.height = width, height

    def _apply_focus(self, mode: str, dioptre: float) -> None:
        try:
            from libcamera import controls
        except ImportError:
            return
        modes = {
            "manual": controls.AfModeEnum.Manual,
            "auto": controls.AfModeEnum.Auto,
            "continuous": controls.AfModeEnum.Continuous,
        }
        if mode not in modes:
            return
        try:
            payload: dict[str, Any] = {"AfMode": modes[mode]}
            if mode == "manual":
                payload["LensPosition"] = float(dioptre)
            self._cam.set_controls(payload)
        except Exception:
            # A fixed-focus module rejects these. Not worth failing a capture over.
            pass

    def grab(self) -> Frame:
        array = self._cam.capture_array()
        # picamera2 hands back RGB; the rest of DiceCore is BGR like the rest of OpenCV.
        try:
            import cv2

            image = cv2.cvtColor(array, cv2.COLOR_RGB2BGR)
        except ImportError:
            image = array[:, :, ::-1]
        h, w = image.shape[:2]
        return Frame(image=image, source=self.name, size=(w, h))

    def close(self) -> None:
        cam = getattr(self, "_cam", None)
        if cam is not None:
            cam.close()
            self._cam = None

    def describe(self) -> dict[str, Any]:
        return {"name": self.name, "width": self.width, "height": self.height}
