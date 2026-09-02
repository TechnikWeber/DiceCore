"""Frame sources, and the one function that picks one from the settings."""

from __future__ import annotations

from ..config import Settings
from .base import CaptureError, FrameSource
from .folder import FolderSource
from .push import PushSource
from .sim import SimSource

#: What the UI offers, in the order it offers it.
SOURCES = (
    ("sim", "Simulated dice — no camera, throw from the screen"),
    ("folder", "Folder of images (played back in order)"),
    ("picamera2", "CSI camera via picamera2"),
    ("rpicam", "CSI camera via rpicam-still"),
    ("v4l2", "USB camera via /dev/video*"),
    ("push", "Frames pushed in from another node"),
)


def open_source(settings: Settings, push: PushSource | None = None) -> FrameSource:
    """
    Build the configured source.

    `picamera2` degrades to `rpicam` on its own, because that pair fails for exactly one
    reason (the system package is not in this venv) and the fallback is always right.
    Everything else fails loudly: silently reading a different camera than the one that was
    configured is how you spend an evening debugging the wrong picture.
    """
    cap = settings.capture
    kind = cap.source

    if kind == "sim":
        return SimSource(cap.width or 900, cap.height or 600)
    if kind == "folder":
        return FolderSource(cap.folder or str(settings.frames_dir))
    if kind == "push":
        return push or PushSource()
    if kind == "v4l2":
        from .v4l2 import V4l2Source

        return V4l2Source(cap.device, cap.width, cap.height)
    if kind == "picamera2":
        from .picamera2_src import Picamera2Source

        try:
            return Picamera2Source(cap.width, cap.height, cap.tuning_file, cap.focus_mode,
                                   cap.focus_dioptre)
        except CaptureError:
            kind = "rpicam"
    if kind == "rpicam":
        from .rpicam import RpicamSource

        return RpicamSource(cap.width, cap.height, cap.tuning_file, cap.focus_mode,
                            cap.focus_dioptre, cap.rotation)
    raise CaptureError(f"Unknown capture source {cap.source!r}. One of: "
                       + ", ".join(name for name, _ in SOURCES))


__all__ = ["CaptureError", "FrameSource", "FolderSource", "PushSource", "SimSource",
           "SOURCES", "open_source"]
