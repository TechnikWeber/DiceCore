"""
The simulator: a directory of images, played back one per `grab()`.

This is what makes the project developable without hardware, and it is not a toy — the
dataset browser, the training preview and the whole test suite run on it. A recorded
session of real rolls replayed through this source is the closest thing to a regression
test that computer vision allows.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..dice import Frame
from .base import CaptureError, FrameSource, require_cv2

SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


class FolderSource(FrameSource):
    name = "folder"

    def __init__(self, folder: str | Path, loop: bool = True) -> None:
        self.folder = Path(folder)
        self.loop = loop
        self._index = 0
        self._files = self._scan()

    def _scan(self) -> list[Path]:
        if not self.folder.is_dir():
            raise CaptureError(f"{self.folder} is not a directory — point capture.folder at one.")
        files = sorted(p for p in self.folder.iterdir() if p.suffix.lower() in SUFFIXES)
        if not files:
            raise CaptureError(
                f"{self.folder} holds no images ({', '.join(sorted(SUFFIXES))}). "
                "Drop a few frames in, or generate some with `dicecore synth`."
            )
        return files

    def grab(self) -> Frame:
        # Re-scan when exhausted so images dropped in while running are picked up: the
        # obvious thing to try when someone is testing is to copy a photo into the folder.
        if self._index >= len(self._files):
            self._files = self._scan()
            if not self.loop:
                raise CaptureError("End of folder reached and loop is off.")
            self._index = 0
        path = self._files[self._index]
        self._index += 1
        cv2 = require_cv2()
        image = cv2.imread(str(path))
        if image is None:
            raise CaptureError(f"{path} could not be decoded.")
        h, w = image.shape[:2]
        return Frame(image=image, at=path.stat().st_mtime,
                     source=f"folder:{path.name}", size=(w, h))

    def describe(self) -> dict[str, Any]:
        return {"name": self.name, "folder": str(self.folder),
                "images": len(self._files), "position": self._index}
