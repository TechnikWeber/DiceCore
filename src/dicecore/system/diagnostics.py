"""
What hardware is actually there, and what to do when it is not.

The parsing lives here (and is tested); the shell calls are thin wrappers, because on a
laptop none of these binaries exist and the whole app still has to come up.
"""

from __future__ import annotations

import glob
import platform
import re
import shutil
import subprocess
from dataclasses import dataclass, field

#: Bookworm renamed libcamera-* to rpicam-*. Try both, newest first.
CAMERA_TOOLS = ("rpicam-hello", "libcamera-hello")

_CAM_LINE = re.compile(r"^\s*(\d+)\s*:\s*(.+)$", re.MULTILINE)


def parse_camera_list(out: str) -> list[str]:
    """Parse the camera list of `rpicam-hello --list-cameras`."""
    return [m.group(2).strip() for m in _CAM_LINE.finditer(out)]


def capture_nodes(paths: list[str]) -> list[str]:
    """
    Which `/dev/video*` nodes are actual capture devices.

    On a Pi, video10 and up are the V4L2 codec/ISP nodes — they exist with no camera
    attached at all, so listing them makes a detection routine claim fourteen cameras on a
    Pi with none.
    """
    out = []
    for p in paths:
        m = re.fullmatch(r"/dev/video(\d+)", p)
        if m and int(m.group(1)) < 10:
            out.append(p)
    return sorted(out, key=lambda p: int(p.rsplit("video", 1)[1]))


def explain_no_camera(tool_found: bool) -> str:
    if not tool_found:
        return (
            "No camera tool found — install rpicam-apps (Raspberry Pi OS Bookworm renamed "
            "libcamera-* to rpicam-*)."
        )
    return (
        "No CSI camera detected. Check the ribbon cable (contacts towards the HDMI side, "
        "CAM port, not DISPLAY). A sensor outside the auto-detect set (Arducam IMX519 / "
        "64MP / Pivariety, OV64A40, …) needs its own dtoverlay — pick it under "
        '"CSI camera module" and reboot.'
    )


def pi_model() -> str | None:
    """`Raspberry Pi Zero 2 W Rev 1.0`, or None on anything that is not a Pi."""
    try:
        with open("/proc/device-tree/model", "rb") as fh:
            return fh.read().decode(errors="replace").strip("\x00").strip() or None
    except OSError:
        return None


@dataclass
class Capabilities:
    """
    What this machine can do — the UI states this plainly instead of offering buttons that
    fail halfway through. An ARMv6 Pi Zero has no PyTorch and no onnxruntime; saying so up
    front is the difference between "use the remote engine" and a confusing stack trace.
    """

    machine: str = field(default_factory=platform.machine)
    pi: str | None = field(default_factory=pi_model)
    numpy: bool = False
    opencv: bool = False
    onnxruntime: bool = False
    torch: bool = False
    picamera2: bool = False

    @property
    def can_run_classic(self) -> bool:
        return self.numpy and self.opencv

    @property
    def can_run_model(self) -> bool:
        return self.onnxruntime and self.numpy

    @property
    def can_train(self) -> bool:
        return self.torch

    def advice(self) -> list[str]:
        out = []
        if not self.can_run_classic:
            out.append(
                "No numpy/OpenCV here, so nothing can be recognised locally. Install the "
                "'vision' extra, or point the engine at another DiceCore node (mode=remote)."
            )
        if not self.can_run_model and self.can_run_classic:
            out.append(
                "onnxruntime is missing, so a trained model cannot run on this machine — "
                "the classic engine still works. On ARMv6 (Pi Zero v1) there are no wheels "
                "at all; use mode=remote there."
            )
        if not self.can_train:
            out.append("PyTorch is missing, so training runs elsewhere. "
                       "Collecting data works fine.")
        return out


def probe() -> Capabilities:
    caps = Capabilities()
    for name in ("numpy", "cv2", "onnxruntime", "torch", "picamera2"):
        try:
            __import__(name)
            found = True
        except Exception:  # a broken install must read as "absent", not crash the probe
            found = False
        setattr(caps, {"cv2": "opencv"}.get(name, name), found)
    return caps


@dataclass
class CameraReport:
    tool: str | None = None
    csi: list[str] = field(default_factory=list)
    video_nodes: list[str] = field(default_factory=list)
    problem: str | None = None


def detect_cameras(timeout_s: float = 8.0) -> CameraReport:
    """Ask the system what cameras exist. Never raises; a failure becomes `problem`."""
    report = CameraReport()
    report.video_nodes = capture_nodes(glob.glob("/dev/video*"))
    tool = next((t for t in CAMERA_TOOLS if shutil.which(t)), None)
    report.tool = tool
    if tool:
        try:
            proc = subprocess.run(
                [tool, "--list-cameras"],
                capture_output=True,
                text=True,
                timeout=timeout_s,
                env={"LC_ALL": "C", "PATH": "/usr/bin:/bin:/usr/local/bin"},
            )
            report.csi = parse_camera_list(proc.stdout)
        except (OSError, subprocess.SubprocessError) as exc:
            report.problem = f"{tool} failed: {exc}"
            return report
    if not report.csi:
        report.problem = explain_no_camera(bool(tool))
    return report
