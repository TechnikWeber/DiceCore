"""
Synthetic dice scenes.

Two jobs, both of which matter more than they look:

* **Tests.** Recognition tests need images with known answers. Photographs cannot be
  committed to a repo in useful numbers, so the suite rolls its own.
* **A first run without hardware.** `dicecore synth` fills a folder that the `folder`
  capture source plays back, so the whole app — UI, API, engine — is usable five minutes
  after cloning, with no camera and no tower.

Synthetic dice are *not* training data. A model trained on these learns to read drawings.
The dataset for training comes from the real camera, through the label loop in the UI.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from pathlib import Path

from .dice import Box

#: Pip positions on the 3x3 face grid, in units of the face width.
_GRID = {
    "tl": (0.25, 0.25), "tc": (0.25, 0.5), "tr": (0.25, 0.75),
    "cl": (0.5, 0.25), "cc": (0.5, 0.5), "cr": (0.5, 0.75),
    "bl": (0.75, 0.25), "bc": (0.75, 0.5), "br": (0.75, 0.75),
}
PIP_LAYOUT = {
    1: ["cc"],
    2: ["tl", "br"],
    3: ["tl", "cc", "br"],
    4: ["tl", "tr", "bl", "br"],
    5: ["tl", "tr", "cc", "bl", "br"],
    6: ["tl", "tr", "cl", "cr", "bl", "br"],
}


@dataclass
class SynthDie:
    kind: str
    value: int
    box: Box
    angle: float


#: Seen from above, a polyhedral die is a polygon with a smaller top face inside it.
#: (silhouette sides, top-face sides) — a d6 is the special case with a square silhouette.
_SHAPE = {
    "d4": (3, 3),
    "d8": (4, 3),
    "d10": (5, 4),
    "d100": (5, 4),
    "d12": (10, 5),
    "d20": (6, 3),
}


def _polygon(size: int, sides: int, radius_frac: float, phase: float = -math.pi / 2):
    import numpy as np

    cx = cy = size / 2
    radius = size * radius_frac
    return np.array(
        [[int(round(cx + radius * math.cos(2 * math.pi * i / sides + phase))),
          int(round(cy + radius * math.sin(2 * math.pi * i / sides + phase)))]
         for i in range(sides)], dtype=np.int32)


def _rounded_mask(size: int, radius: int):
    import cv2
    import numpy as np

    mask = np.zeros((size, size), dtype=np.uint8)
    cv2.rectangle(mask, (radius, 0), (size - radius, size), 255, -1)
    cv2.rectangle(mask, (0, radius), (size, size - radius), 255, -1)
    for cx, cy in ((radius, radius), (size - radius, radius),
                   (radius, size - radius), (size - radius, size - radius)):
        cv2.circle(mask, (cx, cy), radius, 255, -1)
    return mask


def _die_patch(kind: str, value: int, size: int, body, ink, rng: random.Random):
    """
    A single die drawn as seen from above. Rotation and pasting happen in `render_scene`.

    The silhouette matters as much as the number: a d20 from above is a hexagon with a
    triangular face on top, and the engine's job of picking *that* face out of the
    surrounding ones is the whole difficulty with polyhedral dice.
    """
    import cv2
    import numpy as np

    patch = np.zeros((size, size, 3), dtype=np.uint8)
    patch[:] = body

    if kind == "d6":
        mask = _rounded_mask(size, max(2, size // 6))
        pip_r = max(2, int(size * 0.09))
        for key in PIP_LAYOUT[value]:
            fy, fx = _GRID[key]
            cv2.circle(patch, (int(fx * size), int(fy * size)), pip_r, ink, -1, cv2.LINE_AA)
        return _grain(patch, rng), mask

    body_sides, face_sides = _SHAPE.get(kind, (6, 3))
    mask = np.zeros((size, size), dtype=np.uint8)
    cv2.fillPoly(mask, [_polygon(size, body_sides, 0.48)], 255)

    line = max(1, size // 45)
    face = _polygon(size, face_sides, 0.30, phase=-math.pi / 2)
    cv2.polylines(patch, [face], True, ink, line, cv2.LINE_AA)
    # The faces around the top one, faintly — they are what a numeral reader must ignore.
    edge = tuple(int(c * 0.55 + 128 * 0.45) for c in ink)
    for i in range(body_sides):
        a = _polygon(size, body_sides, 0.48)[i]
        b = _polygon(size, face_sides, 0.30)[i % face_sides]
        cv2.line(patch, tuple(int(v) for v in a), tuple(int(v) for v in b), edge, line, cv2.LINE_AA)

    text = f"{value:02d}" if kind == "d100" else str(value)
    scale = size / 75.0
    thickness = max(1, int(size / 28))
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, thickness)
    cx = cy = size / 2
    cv2.putText(patch, text, (int(cx - tw / 2), int(cy + th / 2 + size * 0.04)),
                cv2.FONT_HERSHEY_SIMPLEX, scale, ink, thickness, cv2.LINE_AA)
    if value in (6, 9):
        # The underline convention, because a 6 and a 9 are the same glyph upside down.
        base = int(cy + th * 0.75 + size * 0.04)
        cv2.line(patch, (int(cx - tw / 2), base), (int(cx + tw / 2), base), ink, thickness,
                 cv2.LINE_AA)

    return _grain(patch, rng), mask


def _grain(patch, rng: random.Random):
    """
    Grayscale sensor noise, added in int16 and clipped.

    Per-channel noise added in uint8 wraps around and turns every dark pip into rainbow
    confetti — which is not what a camera does, and it wrecked the first version of this.
    """
    import numpy as np

    amount = rng.randint(2, 8)
    grain = np.random.default_rng(rng.randrange(1 << 30)).integers(
        -amount, amount + 1, patch.shape[:2], dtype=np.int16)
    return np.clip(patch.astype(np.int16) + grain[:, :, None], 0, 255).astype(np.uint8)


def render_scene(
    spec: list[tuple[str, int]],
    width: int = 800,
    height: int = 600,
    seed: int = 0,
    die_px: int = 90,
    tray_bgr: tuple[int, int, int] = (35, 40, 45),
    body_bgr: tuple[int, int, int] = (235, 235, 240),
    ink_bgr: tuple[int, int, int] = (25, 25, 30),
):
    """
    Draw the given dice on a tray and return `(image, ground_truth)`.

    Placement is rejection-sampled so dice never overlap: overlapping dice are a real and
    interesting failure mode, but a test that hits it by accident is just flaky.
    """
    import cv2
    import numpy as np

    rng = random.Random(seed)
    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[:] = tray_bgr
    # A gentle vignette, so the engine is never tested against perfectly even lighting.
    yy, xx = np.mgrid[0:height, 0:width]
    fall = 1.0 - 0.15 * (((xx - width / 2) / (width / 2)) ** 2
                         + ((yy - height / 2) / (height / 2)) ** 2)
    image = np.clip(image * fall[:, :, None], 0, 255).astype(np.uint8)

    truth: list[SynthDie] = []
    for kind, value in spec:
        size = int(die_px * rng.uniform(0.9, 1.1))
        # Rotating inside a same-sized canvas shears the corners off, so the die is drawn
        # into a padded canvas and rotated there. `pad` covers a square's diagonal.
        pad = int(size * 1.5) | 1
        for _ in range(200):
            x = rng.randint(10, max(11, width - pad - 10))
            y = rng.randint(10, max(11, height - pad - 10))
            candidate = Box(x, y, pad, pad)
            if all(not _touches(candidate, Box(d.box.x, d.box.y, pad, pad), margin=6)
                   for d in truth):
                break
        else:
            continue

        angle = rng.uniform(0, 360) if kind != "d6" else rng.uniform(-25, 25)
        patch, mask = _die_patch(kind, value, size, body_bgr, ink_bgr, rng)
        canvas = np.zeros((pad, pad, 3), dtype=np.uint8)
        cmask = np.zeros((pad, pad), dtype=np.uint8)
        off = (pad - size) // 2
        canvas[off:off + size, off:off + size] = patch
        cmask[off:off + size, off:off + size] = mask

        rot = cv2.getRotationMatrix2D((pad / 2, pad / 2), angle, 1.0)
        canvas = cv2.warpAffine(canvas, rot, (pad, pad))
        cmask = cv2.warpAffine(cmask, rot, (pad, pad))
        solid = cmask > 127

        # Shadow first, then the die on top, so the die keeps its own brightness.
        shadow = cv2.GaussianBlur(cmask, (0, 0), size * 0.10).astype(np.float32) / 255.0
        shift = max(3, size // 14)
        sy0, sx0 = y + shift, x + shift
        sy1, sx1 = min(height, sy0 + pad), min(width, sx0 + pad)
        sub = image[sy0:sy1, sx0:sx1].astype(np.float32)
        sh = shadow[: sub.shape[0], : sub.shape[1], None]
        image[sy0:sy1, sx0:sx1] = np.clip(sub * (1 - 0.5 * sh), 0, 255).astype(np.uint8)

        region = image[y:y + pad, x:x + pad]
        np.copyto(region, canvas, where=solid[:, :, None])

        ys, xs = np.nonzero(solid)
        box = Box(x + int(xs.min()), y + int(ys.min()),
                  int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1))
        truth.append(SynthDie(kind, value, box, angle))

    return image, truth


def _touches(a: Box, b: Box, margin: int = 0) -> bool:
    return not (a.x + a.w + margin < b.x or b.x + b.w + margin < a.x
                or a.y + a.h + margin < b.y or b.y + b.h + margin < a.y)


def write_scenes(folder: Path, count: int = 12, seed: int = 1, kinds: tuple[str, ...] = ("d6",)):
    """Fill a folder with rolls so the `folder` capture source has something to play back."""
    import cv2

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    written = []
    for i in range(count):
        spec = []
        for _ in range(rng.randint(1, 3)):
            kind = rng.choice(kinds)
            from .dice import values_for

            spec.append((kind, rng.choice(values_for(kind))))
        image, truth = render_scene(spec, seed=seed + i)
        path = folder / f"synth-{i:03d}.jpg"
        cv2.imwrite(str(path), image)
        written.append((path, truth))
    return written
