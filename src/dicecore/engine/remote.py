"""
Hand the frame to another DiceCore node and use its answer.

This is what makes a weak Pi useful: a Zero captures, a PC or a Pi 5 recognises, and the
consumer of the API cannot tell the difference. Written against `urllib` from the standard
library on purpose — the whole point is that this runs where nothing heavier installs.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
import uuid
from typing import Any

from ..dice import Box, Die, Frame, RollResult
from .base import Engine, EngineError


def encode_jpeg(frame: Frame, quality: int = 85) -> bytes:
    """The frame as JPEG bytes, encoding only if it is not already encoded."""
    if frame.jpeg:
        return frame.jpeg
    if frame.image is None:
        raise EngineError("Frame carries neither pixels nor JPEG data.")
    try:
        import cv2
    except ImportError as exc:
        raise EngineError(
            "Cannot encode this frame without OpenCV. Capture with capture.source=rpicam, "
            "which delivers JPEG straight from the camera and needs no OpenCV."
        ) from exc
    ok, buf = cv2.imencode(".jpg", frame.image, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        raise EngineError("JPEG encoding failed.")
    return buf.tobytes()


def multipart(field: str, filename: str, payload: bytes) -> tuple[bytes, str]:
    """A one-file multipart body. Small enough to not be worth a dependency."""
    boundary = f"----dicecore{uuid.uuid4().hex}"
    body = b"".join([
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'.encode(),
        b"Content-Type: image/jpeg\r\n\r\n",
        payload,
        f"\r\n--{boundary}--\r\n".encode(),
    ])
    return body, f"multipart/form-data; boundary={boundary}"


def result_from_json(data: dict[str, Any], engine: str) -> RollResult:
    """Rebuild a RollResult from a peer's response, tolerating fields we do not know."""
    dice = []
    for raw in data.get("dice", []):
        box = raw.get("box") or {}
        dice.append(Die(
            kind=str(raw.get("kind", "d6")),
            value=int(raw.get("value", 0)),
            box=Box(int(box.get("x", 0)), int(box.get("y", 0)),
                    int(box.get("w", 0)), int(box.get("h", 0))),
            confidence=float(raw.get("confidence", 0.0)),
            alternatives=[int(v) for v in raw.get("alternatives", [])],
        ))
    return RollResult(
        dice=dice,
        engine=engine,
        took_ms=float(data.get("took_ms", 0.0)),
        warnings=list(data.get("warnings", [])),
    )


class RemoteEngine(Engine):
    name = "remote"

    def __init__(self, url: str, timeout_s: float = 5.0, jpeg_quality: int = 85) -> None:
        if not url:
            raise EngineError("engine.remote_url is empty — set it to another node, "
                              "e.g. http://desk.local:8099")
        self.url = url.rstrip("/")
        self.timeout_s = timeout_s
        self.jpeg_quality = jpeg_quality

    def read(self, frame: Frame) -> RollResult:
        payload = encode_jpeg(frame, self.jpeg_quality)
        body, content_type = multipart("image", "frame.jpg", payload)
        request = urllib.request.Request(
            f"{self.url}/api/v1/detect", data=body,
            headers={"Content-Type": content_type, "Accept": "application/json"},
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                data = json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            raise EngineError(f"{self.url} answered {exc.code}: {exc.reason}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise EngineError(
                f"{self.url} is unreachable ({exc}). Is DiceCore running there, and is the "
                "port open?"
            ) from exc
        except ValueError as exc:
            raise EngineError(f"{self.url} did not return JSON.") from exc

        result = result_from_json(data, f"remote:{self.url}")
        # Report the round trip, not the peer's own timing — that is the number that
        # explains a slow read on a split setup.
        result.took_ms = round((time.perf_counter() - started) * 1000, 2)
        return result

    def describe(self) -> dict[str, Any]:
        return {"name": self.name, "url": self.url, "timeout_s": self.timeout_s}
