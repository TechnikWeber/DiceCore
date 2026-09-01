"""
CSI cameras through `rpicam-still`, one still per grab.

Why shell out instead of using picamera2 everywhere: picamera2 is a system package that
does not exist in a plain venv, and on older Pis the libcamera bindings are a moving
target. `rpicam-still -o -` works on every Bookworm Pi, costs a process per frame, and is
exactly right for a dice tower that reads one settled roll — not a 30 fps stream.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import Any

from ..dice import Frame
from .base import CaptureError, FrameSource, require_cv2

TOOLS = ("rpicam-still", "libcamera-still")


class RpicamSource(FrameSource):
    name = "rpicam"

    def __init__(
        self,
        width: int = 1280,
        height: int = 720,
        tuning_file: str = "",
        focus_mode: str = "manual",
        focus_dioptre: float = 0.0,
        rotation: int = 0,
        timeout_s: float = 10.0,
    ) -> None:
        self.tool = next((t for t in TOOLS if shutil.which(t)), None)
        if not self.tool:
            raise CaptureError(
                "Neither rpicam-still nor libcamera-still is installed. "
                "`sudo apt install rpicam-apps` on Raspberry Pi OS Bookworm."
            )
        self.width, self.height = width, height
        self.tuning_file = tuning_file
        self.focus_mode, self.focus_dioptre = focus_mode, focus_dioptre
        self.rotation, self.timeout_s = rotation, timeout_s

    def _argv(self) -> list[str]:
        argv = [
            self.tool,
            "-n",                      # no preview window; this runs headless
            "-t", "300",               # short warm-up: enough for AE/AWB, not a stall
            "--immediate",
            "--width", str(self.width),
            "--height", str(self.height),
            "-o", "-",
            "-e", "jpg",
        ]
        if self.rotation in (90, 180, 270):
            argv += ["--rotation", str(self.rotation)]
        if self.focus_mode in ("auto", "continuous", "manual"):
            argv += ["--autofocus-mode", self.focus_mode]
            if self.focus_mode == "manual":
                argv += ["--lens-position", str(self.focus_dioptre)]
        return argv

    def _env(self) -> dict[str, str]:
        env = {"LC_ALL": "C", "PATH": "/usr/bin:/bin:/usr/local/bin"}
        # LIBCAMERA_RPI_TUNING_FILE is how a tuning file is selected without patching the
        # system-wide one. The Arducam IMX519 needs this or its lens never moves.
        if self.tuning_file:
            env["LIBCAMERA_RPI_TUNING_FILE"] = self.tuning_file
        return env

    def grab(self) -> Frame:
        try:
            proc = subprocess.run(
                self._argv(), capture_output=True, timeout=self.timeout_s, env=self._env()
            )
        except subprocess.TimeoutExpired as exc:
            raise CaptureError(f"{self.tool} timed out after {self.timeout_s}s.") from exc
        except OSError as exc:
            raise CaptureError(f"{self.tool} could not be started: {exc}") from exc
        if proc.returncode != 0 or not proc.stdout:
            err = proc.stderr.decode(errors="replace").strip().splitlines()
            tail = err[-1] if err else f"exit {proc.returncode}"
            raise CaptureError(f"{self.tool} failed: {tail}")
        jpeg = proc.stdout
        cv2 = require_cv2()
        import numpy as np

        image = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise CaptureError(f"{self.tool} returned data that is not a JPEG.")
        h, w = image.shape[:2]
        return Frame(image=image, jpeg=jpeg, source=self.name, size=(w, h))

    def grab_jpeg(self) -> Frame:
        """
        Capture without decoding — the agent shape, for a Pi that only forwards frames.

        Deliberately free of numpy and OpenCV so it works on an ARMv6 Zero.
        """
        try:
            proc = subprocess.run(
                self._argv(), capture_output=True, timeout=self.timeout_s, env=self._env()
            )
        except (subprocess.SubprocessError, OSError) as exc:
            raise CaptureError(f"{self.tool} failed: {exc}") from exc
        if proc.returncode != 0 or not proc.stdout:
            raise CaptureError(f"{self.tool} produced no image (exit {proc.returncode}).")
        return Frame(jpeg=proc.stdout, source=self.name)

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name, "tool": self.tool, "width": self.width, "height": self.height,
            "tuning_file": self.tuning_file, "focus_mode": self.focus_mode,
            "focus_dioptre": self.focus_dioptre,
        }
