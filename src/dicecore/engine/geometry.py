"""
The decisions the classic engine makes, expressed without pixels.

Splitting these out is not tidiness: contour filtering and pip counting are where the
engine goes wrong, and they are only debuggable if they can be tested on numbers instead
of on photographs.
"""

from __future__ import annotations

from ..dice import DIE_FACES, Box

#: Pips only exist in these counts. Anything else means the segmentation was wrong.
VALID_PIP_COUNTS = frozenset(range(1, 7))


def plausible_die(box: Box, frame_area: int, min_area_frac: float, max_area_frac: float,
                  min_aspect: float, max_aspect: float) -> bool:
    """A contour is a die candidate if it is roughly the right size and roughly square."""
    if box.w <= 0 or box.h <= 0 or frame_area <= 0:
        return False
    frac = box.area / frame_area
    if not (min_area_frac <= frac <= max_area_frac):
        return False
    aspect = box.w / box.h
    return min_aspect <= aspect <= max_aspect


def roi_box(frame_w: int, frame_h: int, x: float, y: float, w: float, h: float) -> Box:
    """
    Turn the tray rectangle (fractions of the frame) into pixels, clamped to the frame.

    Fractions rather than pixels so the tray survives a resolution change — the camera
    settings and the tray setup are edited on different days by different people.
    """
    px = max(0, min(frame_w - 1, int(round(x * frame_w))))
    py = max(0, min(frame_h - 1, int(round(y * frame_h))))
    pw = max(1, min(frame_w - px, int(round(w * frame_w))))
    ph = max(1, min(frame_h - py, int(round(h * frame_h))))
    return Box(px, py, pw, ph)


def offset(box: Box, dx: int, dy: int) -> Box:
    """Move a box from ROI coordinates back into full-frame coordinates."""
    return Box(box.x + dx, box.y + dy, box.w, box.h)


def overlaps(a: Box, b: Box, min_iou: float = 0.3) -> bool:
    """Do two candidates describe the same die? Used to drop duplicate contours."""
    ix = max(0, min(a.x + a.w, b.x + b.w) - max(a.x, b.x))
    iy = max(0, min(a.y + a.h, b.y + b.h) - max(a.y, b.y))
    inter = ix * iy
    if inter == 0:
        return False
    union = a.area + b.area - inter
    return union > 0 and inter / union >= min_iou


def pip_confidence(count: int, areas: list[float]) -> float:
    """
    How much to trust a pip count.

    Real pips on one die are the same size; a spread of blob areas means we counted a
    highlight, a shadow edge or half a neighbouring die. That spread is the only signal
    available without a model, so it is what the number is built from.
    """
    if count not in VALID_PIP_COUNTS:
        return 0.0
    if len(areas) < 2:
        return 0.9 if count == 1 else 0.5
    smallest, largest = min(areas), max(areas)
    if largest <= 0:
        return 0.0
    uniformity = smallest / largest          # 1.0 = all pips identical
    return round(min(1.0, 0.55 + 0.45 * uniformity), 3)


def kind_from_size(box: Box, mm_per_px: float) -> str | None:
    """
    Guess the kind from physical size alone.

    Standard sets are close enough in size that this only separates the extremes, so it is
    a hint for the label UI, never a decision: a d20 (~20mm across) against a d6 (~16mm) is
    within the tolerance of a tilted camera. Returns None unless the tray is calibrated.
    """
    if mm_per_px <= 0:
        return None
    mm = max(box.w, box.h) * mm_per_px
    if mm < 10:
        return None
    if mm < 14:
        return "d6"      # small "casino" and board-game dice
    if mm < 18:
        return "d6"
    if mm < 24:
        return "d20"
    return None


def sort_reading_order(boxes: list[Box]) -> list[int]:
    """
    Indices in reading order: top row left-to-right, then the next row.

    Dice have no inherent order, but a list that reshuffles between two reads of the same
    settled scene makes the label UI unusable — "the second die" has to keep meaning the
    same die.
    """
    if not boxes:
        return []
    # Bucketing by `y // row_height` looks equivalent and is not: two dice at y=8 and y=10
    # land in different buckets whenever a bucket edge falls between them. Group by the
    # gap to the previous die instead, which has no edges to fall between.
    tolerance = max(1, max(b.h for b in boxes) // 2)
    by_y = sorted(range(len(boxes)), key=lambda i: boxes[i].center[1])
    rows: list[list[int]] = []
    for i in by_y:
        if rows and boxes[i].center[1] - boxes[rows[-1][-1]].center[1] <= tolerance:
            rows[-1].append(i)
        else:
            rows.append([i])
    return [i for row in rows for i in sorted(row, key=lambda j: boxes[j].center[0])]


def kinds_are_known(kinds: list[str]) -> bool:
    return all(k in DIE_FACES for k in kinds)
