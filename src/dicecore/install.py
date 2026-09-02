"""
Installing the optional halves of DiceCore from inside DiceCore.

PyTorch is two gigabytes and is only needed on the machine that trains. Telling somebody to
open a terminal, find the right virtualenv and remember the extra's name is a fine way to
lose them at exactly the point where the project starts being interesting — so the Training
page offers a button, and this is what it presses.

**The extra is chosen from a fixed list, never from what was sent.** An endpoint that hands
a user-supplied string to `pip install` is remote code execution with a friendly label on
it; there is no version of that which is acceptable, so the request carries a key and the
key selects a constant.
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: key → (what it is for, the extra as written in pyproject.toml)
EXTRAS: dict[str, tuple[str, str]] = {
    "train": ("Training models on this machine (PyTorch, ~2 GB)", "train"),
    "model": ("Running a trained model here (onnxruntime)", "model"),
    "vision": ("Reading dice here at all (numpy, OpenCV)", "vision"),
    "display": ("A small screen over the tower (luma, Pillow)", "display"),
    "gpio": ("Lamps, buzzer and buttons (gpiozero)", "gpio"),
}

#: Keep the log bounded: pip is chatty and a Pi has no memory to spare for it.
MAX_LINES = 200


@dataclass
class InstallJob:
    extra: str
    state: str = "running"        # running | done | failed
    started: float = field(default_factory=time.time)
    finished: float | None = None
    lines: list[str] = field(default_factory=list)
    error: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {"extra": self.extra, "state": self.state, "started": self.started,
                "finished": self.finished, "lines": self.lines[-40:], "error": self.error,
                "elapsed_s": round((self.finished or time.time()) - self.started, 1)}


def package_spec(extra: str) -> str:
    """
    What to hand pip: the checkout if we are running from one, the published name otherwise.

    Installing `dicecore[train]` from PyPI over an editable checkout would replace the code
    that is running with a different copy, which is a strange thing to do to somebody who
    pressed a button labelled "install PyTorch".
    """
    root = Path(__file__).resolve().parents[2]
    if (root / "pyproject.toml").is_file():
        return f"{root}[{extra}]"
    return f"dicecore[{extra}]"


class Installer:
    """One installation at a time, on a thread, with its output kept for the page."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.job: InstallJob | None = None
        self._thread: threading.Thread | None = None

    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, key: str) -> InstallJob:
        if key not in EXTRAS:
            raise ValueError(f"Unknown extra {key!r}. One of: {', '.join(EXTRAS)}")
        with self._lock:
            if self.running():
                raise RuntimeError("An install is already running.")
            job = InstallJob(extra=key)
            self.job = job
            self._thread = threading.Thread(target=self._run, args=(job,),
                                            name="dicecore-install", daemon=True)
            self._thread.start()
            return job

    def _run(self, job: InstallJob) -> None:
        _, extra = EXTRAS[job.extra]
        editable = package_spec(extra)
        argv = [sys.executable, "-m", "pip", "install"]
        if not editable.startswith("dicecore["):
            argv.append("-e")
        argv.append(editable)
        job.lines.append("$ " + " ".join(argv))
        try:
            process = subprocess.Popen(argv, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, text=True, bufsize=1)
            assert process.stdout is not None
            for line in process.stdout:
                job.lines.append(line.rstrip())
                del job.lines[:-MAX_LINES]
            code = process.wait()
        except Exception as exc:
            job.state, job.error = "failed", str(exc)
            job.finished = time.time()
            return
        job.finished = time.time()
        if code == 0:
            job.state = "done"
            job.lines.append("— installed. Restart DiceCore to pick it up.")
        else:
            job.state = "failed"
            job.error = f"pip exited {code}"


def available() -> dict[str, dict[str, Any]]:
    """Which extras are already here, so the page offers only what is missing."""
    checks = {"train": "torch", "model": "onnxruntime", "vision": "cv2",
              "display": "luma.core", "gpio": "gpiozero"}
    out = {}
    for key, (why, _) in EXTRAS.items():
        module = checks[key]
        try:
            __import__(module)
            installed = True
        except Exception:
            installed = False
        out[key] = {"why": why, "installed": installed}
    return out
