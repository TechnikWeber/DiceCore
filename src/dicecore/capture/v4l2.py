"""USB cameras (and CSI cameras exposed as /dev/video*) through OpenCV."""

from __future__ import annotations

from typing import Any

from ..dice import Frame
from .base import CaptureError, FrameSource, require_cv2


class V4l2Source(FrameSource):
    name = "v4l2"

    def __init__(self, device: int = 0, width: int = 1280, height: int = 720) -> None:
        cv2 = require_cv2()
        self.device, self.width, self.height = device, width, height
        self._cap = cv2.VideoCapture(device)
        if not self._cap.isOpened():
            raise CaptureError(
                f"/dev/video{device} did not open. Check `v4l2-ctl --list-devices`, and that "
                "nothing else holds the camera."
            )
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

    def grab(self) -> Frame:
        # The first frames out of a webcam are often black or auto-exposing; the caller
        # deals with that through settle detection rather than a sleep here.
        ok, image = self._cap.read()
        if not ok or image is None:
            raise CaptureError(f"/dev/video{self.device} stopped delivering frames.")
        h, w = image.shape[:2]
        return Frame(image=image, source=f"v4l2:{self.device}", size=(w, h))

    def close(self) -> None:
        if getattr(self, "_cap", None) is not None:
            self._cap.release()
            self._cap = None

    def describe(self) -> dict[str, Any]:
        return {"name": self.name, "device": self.device,
                "width": self.width, "height": self.height}
