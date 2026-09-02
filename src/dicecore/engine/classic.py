"""
The engine that needs no training.

Scope, stated honestly: it segments dice against the tray and counts **pips**. That covers
d6 (and the pipped faces of a d10 set) in decent light on a contrasting tray, which is
enough to make the whole project useful on the day it is installed, and it stays useful
afterwards as the fallback when no model is loaded.

It does *not* read numerals. A candidate whose pips do not add up to a legal count is
reported with `value=0` and `confidence=0` rather than guessed at — a wrong number that
looks confident is worse than an honest "I need a model for this one", and that report is
exactly what the label UI turns into training data.

Everything the pipeline decides on numbers rather than pixels lives in `geometry.py`.
"""

from __future__ import annotations

import time
from typing import Any

from ..config import ClassicSettings, Settings, TraySettings
from ..dice import Box, Die, Frame, RollResult
from . import colour as colours
from . import geometry as geo
from .base import Engine, EngineError


class ClassicEngine(Engine):
    name = "classic"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        try:
            import cv2  # noqa: F401
            import numpy  # noqa: F401
        except ImportError as exc:
            raise EngineError(
                "The classic engine needs numpy and OpenCV: `pip install 'dicecore[vision]'`. "
                "On a Pi Zero v1 install neither — point engine.mode at 'remote' instead."
            ) from exc

    # --- the pipeline ---------------------------------------------------------

    def read(self, frame: Frame) -> RollResult:
        import cv2
        import numpy as np

        started = time.perf_counter()
        if frame.image is None:
            raise EngineError("The classic engine needs decoded pixels, not just a JPEG.")

        cfg = self.settings.classic
        tray = self.settings.tray
        warnings: list[str] = []

        full = frame.image
        h, w = full.shape[:2]
        roi = geo.roi_box(w, h, tray.x, tray.y, tray.w, tray.h)
        crop = full[roi.y:roi.y + roi.h, roi.x:roi.x + roi.w]

        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
        if cfg.blur > 0:
            k = cfg.blur | 1  # OpenCV insists on an odd kernel
            gray = cv2.GaussianBlur(gray, (k, k), 0)

        mode = cv2.THRESH_BINARY if cfg.dice_are_light else cv2.THRESH_BINARY_INV
        _, mask = cv2.threshold(gray, 0, 255, mode | cv2.THRESH_OTSU)
        # Close first, then open: closing fills the pips so a die is one solid blob (a die
        # read as six separate pip-holes is the classic failure), opening then removes the
        # speckle that closing amplified.
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=3)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        area = roi.w * roi.h

        candidates: list[tuple[Box, Any]] = []
        for contour in contours:
            x, y, cw, ch = cv2.boundingRect(contour)
            box = Box(int(x), int(y), int(cw), int(ch))
            if not geo.plausible_die(box, area, cfg.min_area_frac, cfg.max_area_frac,
                                     cfg.min_aspect, cfg.max_aspect):
                continue
            if any(geo.overlaps(box, other) for other, _ in candidates):
                continue
            candidates.append((box, contour))

        dice: list[Die] = []
        for box, contour in candidates:
            die_mask = np.zeros(gray.shape, dtype=np.uint8)
            cv2.drawContours(die_mask, [contour], -1, 255, -1)
            count, areas = self._count_pips(gray, die_mask, box, cfg)
            confidence = geo.pip_confidence(count, areas)
            name = None
            if cfg.detect_colour and crop.ndim == 3:
                # Sampled from the whole die, pips and highlights trimmed off inside
                # `colour.sample` — see there for why the median and not the mean.
                inset = cv2.erode(die_mask, cv2.getStructuringElement(
                    cv2.MORPH_ELLIPSE, (5, 5)), iterations=2)
                name = colours.sample(crop, inset)[0]
            if confidence > 0:
                dice.append(Die("d6", count, geo.offset(box, roi.x, roi.y), confidence,
                                colour=name))
            else:
                kind = geo.guess_unread_kind(box, tray.mm_per_px,
                                             self.settings.engine.expected_kinds)
                dice.append(Die(kind, 0, geo.offset(box, roi.x, roi.y), 0.0, colour=name))

        order = geo.sort_reading_order([d.box for d in dice])
        dice = [dice[i] for i in order]

        unread = sum(1 for d in dice if d.confidence == 0)
        if unread:
            warnings.append(
                f"{unread} of {len(dice)} dice could not be read by pip counting. The classic "
                "engine reads pips only — label them under Training to teach a model the "
                "numerals."
            )
        if not dice:
            warnings.append(
                "No dice found. Check the tray region and the contrast setting "
                "(classic.dice_are_light), and that the tray is actually in frame."
            )

        return RollResult(
            dice=dice,
            engine=self.name,
            took_ms=round((time.perf_counter() - started) * 1000, 2),
            warnings=warnings,
        )

    def _count_pips(self, gray: Any, die_mask: Any, box: Box,
                    cfg: ClassicSettings) -> tuple[int, list[float]]:
        """
        Count the dark blobs inside one die.

        Thresholding happens on the die's own pixels, not the frame's: a bright die next to
        a shadowed one have different "dark" and a single global threshold gets one of them
        wrong every time.
        """
        import cv2
        import numpy as np

        x, y, w, h = box.x, box.y, box.w, box.h
        # Shrink inwards: the die's own outline and its shadow are the strongest dark edges
        # in the crop, and without this margin they are counted as pips.
        inset = max(2, int(min(w, h) * 0.10))
        sub_mask = die_mask[y:y + h, x:x + w].copy()
        sub_mask = cv2.erode(sub_mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                                                                 (inset, inset)))
        sub = gray[y:y + h, x:x + w]
        face = sub[sub_mask > 0]
        if face.size < 25:
            return 0, []

        # Otsu on the face pixels alone. Feeding it the whole crop would put the threshold
        # between "die" and "tray" instead of between "face" and "pip".
        threshold, _ = cv2.threshold(face, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        spread = float(face.max()) - float(face.min())
        if spread < 30:
            return 0, []  # a blank face, or a die too small to resolve pips
        # Which side of the threshold the pips are on is a property of the dice, not of the
        # light: a black die with white pips has no dark blobs to find at all.
        inked = sub < threshold if cfg.pips_are_dark else sub > threshold
        pips = np.where(inked & (sub_mask > 0), 255, 0).astype(np.uint8)
        pips = cv2.morphologyEx(pips, cv2.MORPH_OPEN,
                                cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))

        contours, _ = cv2.findContours(pips, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        die_area = float(w * h)
        areas: list[float] = []
        for contour in contours:
            pip_area = cv2.contourArea(contour)
            frac = pip_area / die_area
            if not (cfg.min_pip_area_frac <= frac <= cfg.max_pip_area_frac):
                continue
            perimeter = cv2.arcLength(contour, True)
            if perimeter <= 0:
                continue
            # Pips are round. Numerals, engraved edges and highlights are not, and this is
            # what keeps a numeral die from being reported as a confident d6.
            circularity = 4 * np.pi * pip_area / (perimeter * perimeter)
            if circularity < 0.6:
                continue
            areas.append(pip_area)
        return len(areas), areas

    def describe(self) -> dict[str, Any]:
        return {"name": self.name, "reads": ["pips (d6)"], "trained": False,
                "colour": self.settings.classic.detect_colour}


def tray_preview(settings: TraySettings, frame_w: int, frame_h: int) -> Box:
    """The tray rectangle in pixels — the UI draws this over the live frame."""
    return geo.roi_box(frame_w, frame_h, settings.x, settings.y, settings.w, settings.h)
