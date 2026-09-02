"""
Waiting for the dice to stop.

A frame grabbed mid-tumble is worthless, and "wait two seconds" is wrong in both
directions — too slow for a d6 that lands flat, too fast for a d20 that rolls off the ramp.
So: watch the frame difference, and read once it has been quiet for a few frames in a row.

The measure is the mean absolute difference of a downscaled grayscale frame. Downscaling
first is not an optimisation, it is what makes the number meaningful: at full resolution,
sensor noise and JPEG blocking alone produce a few counts of difference on a perfectly
still scene.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..config import SettleSettings
from ..dice import Frame

#: Every frame is reduced to this width before differencing.
WORK_WIDTH = 160


def motion_score(previous: Any, current: Any) -> float:
    """Mean absolute difference (0..255) between two prepared frames."""
    import numpy as np

    return float(np.mean(np.abs(previous.astype("int16") - current.astype("int16"))))


def prepare(image: Any) -> Any:
    """Grayscale, small, blurred — the form motion is measured in."""
    import cv2

    h, w = image.shape[:2]
    scale = WORK_WIDTH / float(w) if w > WORK_WIDTH else 1.0
    small = cv2.resize(image, (int(w * scale), int(h * scale))) if scale != 1.0 else image
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY) if small.ndim == 3 else small
    return cv2.GaussianBlur(gray, (5, 5), 0)


@dataclass
class SettleResult:
    frame: Frame
    settled: bool
    frames_seen: int
    waited_s: float
    last_motion: float
    #: The largest motion seen while waiting. Zero means the dice never moved at all, which
    #: is how "nothing was thrown, this is the previous roll" is told from a real throw.
    peak_motion: float = 0.0

    @property
    def warning(self) -> str | None:
        if self.settled:
            return None
        return (
            f"Read after {self.waited_s:.1f}s without the scene going still "
            f"(motion {self.last_motion:.1f}). A die may still have been rolling."
        )


def wait_for_settle(
    grab: Callable[[], Frame],
    settings: SettleSettings,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
) -> SettleResult:
    """
    Grab until the scene stops moving, then return the last frame.

    `sleep` and `now` are injectable so the tests can run this instantly instead of in real
    seconds — settle logic is exactly the kind of thing that is only wrong at the edges.
    """
    started = now()
    frame = grab()
    if not settings.enabled:
        return SettleResult(frame, True, 1, 0.0, 0.0, 0.0)

    previous = prepare(frame.image)
    still = 0
    seen = 1
    motion = 0.0
    peak = 0.0
    while now() - started < settings.timeout_s:
        sleep(0.05)
        frame = grab()
        seen += 1
        current = prepare(frame.image)
        motion = motion_score(previous, current)
        peak = max(peak, motion)
        previous = current
        still = still + 1 if motion <= settings.motion_threshold else 0
        if still >= settings.stable_frames:
            return SettleResult(frame, True, seen, now() - started, motion, peak)
    return SettleResult(frame, False, seen, now() - started, motion, peak)
