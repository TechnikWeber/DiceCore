"""
The capture interface: one method, `grab()`, returning a `Frame`.

Kept this small on purpose. Every deployment shape in docs/CONCEPT.md — Pi with a CSI
camera, USB webcam, a folder of JPEGs on a laptop, frames pushed in over HTTP from another
node — is one implementation of this, and the rest of DiceCore cannot tell them apart.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any

from ..dice import Frame


class CaptureError(RuntimeError):
    """Capture failed in a way the user has to fix (no camera, empty folder, bad device)."""


class FrameSource(ABC):
    #: Identifier used in `Frame.source` and in the UI.
    name = "base"
    #: Whether every grab is a genuinely new look at the world. False for the folder
    #: simulator and for pushed frames, where the same image legitimately comes back twice.
    #: The tamper guard's frozen-feed check only means something on a live source.
    is_live = True

    @abstractmethod
    def grab(self) -> Frame:
        """Return the current frame. Raises CaptureError with a human-readable reason."""

    def close(self) -> None:
        """Release the device. Safe to call twice."""

    def throw(self) -> list[tuple[str, int]]:
        """
        Roll new dice, for the sources that can. A camera cannot: the dice on its tray are
        the ones somebody threw, and no amount of asking changes them.
        """
        raise CaptureError("This source reads dice; it cannot throw them.")

    def hold(self, enabled: bool) -> None:
        """
        Stay on the current scene while the tamper guard watches it.

        A no-op for a real camera, which is already pointed at one tray and keeps
        delivering it. It exists for the sources that advance on their own — the folder
        simulator hands out the *next* roll on every grab, and without this the guard would
        see a completely different tray a tenth of a second later and call it tampering.
        """

    def describe(self) -> dict[str, Any]:
        """What the UI shows about this source."""
        return {"name": self.name}

    def __enter__(self) -> FrameSource:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def require_numpy() -> Any:
    """
    Import numpy with an explanation instead of an ImportError.

    The base install deliberately has no numpy so that the agent shape fits on an ARMv6
    Pi Zero; anything that needs pixels has to say so clearly.
    """
    try:
        import numpy
    except ImportError as exc:  # pragma: no cover - depends on the install
        raise CaptureError(
            "This needs numpy, which is not installed. `pip install 'dicecore[vision]'` — "
            "or run the engine on another machine (engine.mode=remote)."
        ) from exc
    return numpy


def require_cv2() -> Any:
    try:
        import cv2
    except ImportError as exc:  # pragma: no cover - depends on the install
        raise CaptureError(
            "This needs OpenCV, which is not installed. `pip install 'dicecore[vision]'` — "
            "or run the engine on another machine (engine.mode=remote)."
        ) from exc
    return cv2


def require_tuning_file(path: str) -> None:
    """
    Refuse to start a camera with a tuning file that is not there.

    libcamera does not degrade when `LIBCAMERA_RPI_TUNING_FILE` points at nothing: it fails
    to load the IPA, refuses to register the sensor, and `rpicam-still` answers *no cameras
    available* — which reads exactly like an unplugged ribbon cable and sends people back to
    the hardware for a setting. Saying so here is the difference between a five-minute fix
    and an evening with a screwdriver.
    """
    if path and not os.path.isfile(path):
        raise CaptureError(
            f"The tuning file {path} does not exist, and libcamera refuses to open the "
            "camera at all when one is missing (it reports 'no cameras available', which "
            "looks like a cable fault). Clear Camera → Tuning file, or press "
            "\"Apply module\" again, which only sets one that is actually installed."
        )
