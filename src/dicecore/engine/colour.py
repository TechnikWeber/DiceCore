"""
Which colour a die is.

Optional, and off by default: it costs a little work per die and most games do not care.
Where it matters is the family of games that are *about* the colours — Qwixx, Sagrada, King
of Tokyo, Las Vegas — and telling one player's dice from another's on a shared tray.

The classification is a pure function of hue, saturation and value, so what counts as "red"
is a question the test suite can answer. The sampling lives in `classic.py`, where the
pixels are.

Two things it deliberately does not do. It does not try to name a shade: "red" and "orange"
are as fine as a camera under a table lamp can honestly be. And it never *decides* anything
— the colour rides along on the result, and a game that wants to use it says so.
"""

from __future__ import annotations

from typing import Any

#: What a die may come back as. `unknown` is a real answer, not a failure.
NAMES = ("white", "black", "grey", "red", "orange", "yellow", "green", "cyan", "blue",
         "purple", "pink", "unknown")

#: A representative swatch per name, for drawing the die on a screen.
SWATCH = {
    "white": "#eef1f5", "black": "#23262c", "grey": "#8b93a1", "red": "#e5484d",
    "orange": "#f0862a", "yellow": "#f5d020", "green": "#3ecf8e", "cyan": "#3fc5d8",
    "blue": "#4f7ff5", "purple": "#a濃".replace("濃", "56ef0"), "pink": "#f472b6",
    "unknown": "#6b7280",
}

#: Hue bands in OpenCV's 0–179 scale. Red wraps, so it appears at both ends.
BANDS = (
    (0, 9, "red"), (9, 21, "orange"), (21, 34, "yellow"), (34, 85, "green"),
    (85, 100, "cyan"), (100, 130, "blue"), (130, 152, "purple"), (152, 170, "pink"),
    (170, 180, "red"),
)

#: Below this saturation a pixel has no colour worth naming, only a brightness.
GREY_SATURATION = 60
#: Below this value it is dark whatever the hue says.
DARK_VALUE = 60
#: Above this value with no saturation it is white rather than grey.
WHITE_VALUE = 165


def classify(hue: float, saturation: float, value: float) -> str:
    """
    Name a colour from an HSV sample, in OpenCV's ranges (H 0–179, S and V 0–255).

    Order matters: brightness is decided before hue, because a black die under a warm lamp
    has a perfectly confident hue and it means nothing at all.
    """
    if value < DARK_VALUE:
        return "black"
    if saturation < GREY_SATURATION:
        return "white" if value >= WHITE_VALUE else "grey"
    for low, high, name in BANDS:
        if low <= hue < high:
            return name
    return "unknown"


def swatch(name: str) -> str:
    return SWATCH.get(name, SWATCH["unknown"])


def sample(image: Any, mask: Any) -> tuple[str, tuple[int, int, int]]:
    """
    The body colour of one die: the median of its own pixels, pips and highlights removed.

    The median, and nothing else. A die's face is mostly body colour interrupted by two
    things that are not it — the ink of the pips and the reflection of the lamp — and since
    the body is always more than half the pixels, the median lands on it by construction.

    An earlier version trimmed the darkest quarter first, which works for a white die and
    is exactly wrong for a black one: there the ink is the *bright* part, and cutting the
    dark quarter left the sample looking at the pips. The median needs no such guess.
    """
    import cv2
    import numpy as np

    pixels = image[mask > 0]
    if pixels.size < 30:
        return "unknown", (0, 0, 0)
    hsv = cv2.cvtColor(pixels.reshape(-1, 1, 3), cv2.COLOR_BGR2HSV).reshape(-1, 3)
    # Hue is an angle, so it is averaged on the circle — otherwise red, which sits at both
    # ends of the scale, averages to cyan. Weighted by saturation, so the grey pixels of a
    # pip do not drag the hue of a coloured die about.
    weight = hsv[:, 1].astype("float32")
    angle = np.deg2rad(hsv[:, 0].astype("float32") * 2.0)
    if weight.sum() > 0:
        mean_hue = (np.rad2deg(np.arctan2(
            (np.sin(angle) * weight).sum(), (np.cos(angle) * weight).sum())) % 360) / 2.0
    else:
        mean_hue = float(np.median(hsv[:, 0]))
    saturation = float(np.median(hsv[:, 1]))
    brightness = float(np.median(hsv[:, 2]))
    return classify(mean_hue, saturation, brightness), (
        int(mean_hue), int(saturation), int(brightness))
