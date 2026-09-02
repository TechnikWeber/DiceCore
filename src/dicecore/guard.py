"""
Watching the tray after the number has been read.

The sequence a roll goes through:

    thrown ──► tumbling ──► still ──► READ ──► held (this module) ──► verdict

Settling (`capture/settle.py`) answers *when* to look. This answers *whether what was
looked at is still true*. For `hold_s` after the reading the tray is watched; anything that
moves is recorded, and at the end the dice are read a second time and compared with what
was published. A hand in the tray is suspicious; a **changed reading** is disqualifying.

Why re-read rather than trust the motion signal alone: motion tells you something happened,
not what. Someone reaching past the tower for their drink casts a shadow across the tray and
must not throw away a legitimate roll, while a die turned over quickly enough to sit between
two frames must not slip through. Comparing the readings answers the question the motion
score only hints at.

Everything decided here is in `integrity.py` and is tested on numbers. This file only turns
pixels into events.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .capture.settle import WORK_WIDTH, motion_score, prepare
from .config import GuardSettings
from .dice import Box, Die, Frame
from .integrity import (
    FAULT,
    INFO,
    SUPERSEDED,
    WARN,
    Event,
    Integrity,
    decide,
    seal,
)


@dataclass
class Watch:
    """State of one hold window. Kept explicit so the UI can show it while it runs."""

    started: float
    events: list[Event] = field(default_factory=list)
    frames: int = 0
    peak_motion: float = 0.0

    def add(self, kind: str, severity: str, detail: str) -> None:
        # One event per kind per window. A hand waving over the tray for two seconds is one
        # reach, not forty, and a log that says it forty times hides the one that matters.
        if any(e.kind == kind for e in self.events):
            return
        self.events.append(Event(kind, severity, detail))


def change_boxes(before: Any, after: Any, threshold: int = 25, min_area: int = 12
                 ) -> list[Box]:
    """
    Where two prepared frames differ, as boxes in prepared (small) coordinates.

    Works on the same downscaled grayscale frames the settle detector uses — at full
    resolution, sensor noise alone lights up the whole frame, and on a Pi Zero the cost of
    doing this per frame would matter.
    """
    import cv2

    diff = cv2.absdiff(before, after)
    _, mask = cv2.threshold(diff, threshold, 255, cv2.THRESH_BINARY)
    mask = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)), iterations=2)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w * h >= min_area:
            boxes.append(Box(int(x), int(y), int(w), int(h)))
    return sorted(boxes, key=lambda b: -b.area)


def touches_border(box: Box, width: int, height: int, margin: int = 3) -> bool:
    """
    Does this change reach the edge of the frame?

    An arm has to come in from outside, so a change region that touches the border and is
    large is a hand — while a die that turned over is an interior blob the size of a die.
    Not proof (a tray can extend past the frame), which is why this only sets the wording of
    the event, never the verdict on its own.
    """
    return (box.x <= margin or box.y <= margin
            or box.x + box.w >= width - margin or box.y + box.h >= height - margin)


def describe_change(boxes: list[Box], width: int, height: int, hand_area_frac: float
                    ) -> tuple[str, str]:
    """`(kind, wording)` for the largest change region: a reach, a moved die, or noise."""
    if not boxes:
        return "motion", "the picture changed but nothing stood out"
    biggest = boxes[0]
    frac = biggest.area / float(max(1, width * height))
    if frac >= hand_area_frac and touches_border(biggest, width, height):
        return "reach", f"something entered the tray from outside ({frac:.0%} of the frame)"
    if frac >= hand_area_frac:
        return "reach", f"a large object appeared over the tray ({frac:.0%} of the frame)"
    return "motion", f"something moved on the tray ({len(boxes)} spot(s))"


class TamperGuard:
    """
    Holds the tray under watch for one roll.

    Driven by callables rather than by a `Reader` so the tests can run a whole hold window
    in fake time, with scripted frames, and without a camera.
    """

    def __init__(self, settings: GuardSettings) -> None:
        self.settings = settings

    def watch(
        self,
        grab: Callable[[], Frame],
        reread: Callable[[Frame], list[Die]],
        sealed: list[Die],
        reference: Frame,
        jpeg: bytes | None = None,
        prior_events: list[Event] | None = None,
        live: bool = True,
        should_stop: Callable[[], bool] = lambda: False,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], float] = time.monotonic,
    ) -> Integrity:
        """
        Watch until `hold_s` has passed, then check the dice again.

        Returns the `Integrity` record to attach to the result. Never raises for a capture
        failure during the window — a camera that drops out mid-hold is itself an event
        worth reporting, not a crash that loses the roll.
        """
        cfg = self.settings
        integrity = Integrity(seal=seal(jpeg, sealed))
        if not cfg.enabled or cfg.policy == "off":
            integrity.events = list(prior_events or [])
            integrity.verdict = decide([], "off")
            return integrity

        # Events the caller already established — a frozen feed spotted between rolls, a
        # reading that was never thrown — count towards the verdict like any other.
        watch = Watch(started=now(), events=list(prior_events or []))
        baseline = prepare(reference.image)
        previous = baseline
        previous_raw = pixel_fingerprint(reference.image)
        identical_runs = 0
        latest = reference

        while now() - watch.started < cfg.hold_s:
            if should_stop():
                # The next roll has begun. Re-reading now would compare this roll against a
                # tray that is deliberately full of different dice, so stop here and say so
                # rather than inventing a fault out of normal play.
                integrity.held_s = now() - watch.started
                integrity.events = watch.events
                integrity.verdict = SUPERSEDED
                return integrity
            sleep(cfg.interval_s)
            try:
                latest = grab()
            except Exception as exc:
                watch.add("capture", FAULT, f"the camera stopped during the hold: {exc}")
                break
            watch.frames += 1
            current = prepare(latest.image)
            motion = motion_score(previous, current)
            watch.peak_motion = max(watch.peak_motion, motion)

            # Frozen-feed detection deliberately compares the *raw* pixels, not the
            # downscaled ones the motion score uses: after a resize and a blur, two
            # genuinely different captures of a still tray come out identical all the time,
            # and checking there would call every quiet table a frozen feed. At full
            # resolution a real sensor never repeats exactly. On a source that is not live
            # the repeat is legitimate, so the check is skipped rather than lied about.
            raw = pixel_fingerprint(latest.image)
            if live and raw == previous_raw:
                identical_runs += 1
                if identical_runs == cfg.freeze_frames:
                    watch.add("frozen", FAULT,
                              f"{cfg.freeze_frames} identical captures in a row — the video "
                              "feed is frozen or replayed, not the dice lying still")
            else:
                identical_runs = 0
            previous_raw = raw

            if self._too_dark(current, baseline, cfg):
                watch.add("obscured", FAULT, "the tray went dark — the camera was covered")

            if motion > cfg.motion_threshold:
                boxes = change_boxes(baseline, current)
                height, width = current.shape[:2]
                kind, wording = describe_change(boxes, width, height, cfg.hand_area_frac)
                watch.add(kind, WARN, wording)

        integrity.held_s = now() - watch.started

        # The check that decides it: are the dice still what we published?
        if any(e.kind in ("reach", "motion", "frozen", "obscured", "capture")
               for e in watch.events) or cfg.always_recheck:
            try:
                after = reread(latest)
            except Exception as exc:
                watch.add("recheck", WARN, f"the tray could not be read again: {exc}")
                after = None
            if after is not None:
                integrity.settled_check = True
                from .integrity import compare_readings

                differences = compare_readings(sealed, after, cfg.move_tolerance)
                for difference in differences:
                    watch.add("changed", FAULT, difference)
                if not differences and watch.events:
                    watch.add("unchanged", INFO,
                              "the tray was disturbed but the dice read the same afterwards")
        else:
            integrity.settled_check = True

        integrity.events = watch.events
        integrity.verdict = decide(watch.events, cfg.policy, cfg.void_on_touch)
        return integrity

    @staticmethod
    def _too_dark(current: Any, baseline: Any, cfg: GuardSettings) -> bool:
        """A collapse in brightness relative to the frame the reading came from."""
        import numpy as np

        before, after = float(np.mean(baseline)), float(np.mean(current))
        return before > 5 and after < before * cfg.dark_fraction


def pixel_fingerprint(image: Any) -> bytes:
    """
    A cheap identity for one captured frame.

    Every seventh pixel is enough: two captures from a real sensor differ in thousands of
    them, and hashing the full 2.7 MB of a 1280x720 frame every 150 ms is a cost a Pi does
    not need to pay to learn the same thing.
    """
    import hashlib

    return hashlib.blake2b(image[::7, ::7].tobytes(), digest_size=16).digest()


def prepared_size(image: Any) -> tuple[int, int]:
    """The working resolution a frame is reduced to — useful for the UI's own overlays."""
    h, w = image.shape[:2]
    scale = WORK_WIDTH / float(w) if w > WORK_WIDTH else 1.0
    return int(w * scale), int(h * scale)
