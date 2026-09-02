"""
Drawing the number for a small screen.

One renderer for every display, because a 128×64 monochrome OLED and a 240×320 colour LCD
should say the *same thing* — they only differ in how much room there is to say it in. Every
size here is derived from the panel's own height, so a 135×240 stick and a 320×240 tile both
come out looking deliberate instead of cropped.

The screen has one job: from across the table, tell you the number and whether it is your
turn. Everything else is decoration and gets dropped first when the panel is small.
"""

from __future__ import annotations

from typing import Any

from .state import ERROR, IDLE, READING, READY, RESULT, ROLLING, VOID, Presentation

#: Tried in order. Pi OS ships DejaVu; the rest are what other distributions have.
FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/liberation-sans-fonts/LiberationSans-Bold.ttf",
    "/usr/share/fonts/google-noto/NotoSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
)

#: Phase → (background, ink, accent). Colour is the message from across the room: green you
#: may throw, amber the tray is being watched, red do not count this.
PALETTE = {
    IDLE:    ((14, 16, 20), (150, 160, 175), (60, 190, 120)),
    ROLLING: ((14, 16, 20), (210, 215, 225), (90, 140, 250)),
    READING: ((14, 16, 20), (210, 215, 225), (90, 140, 250)),
    RESULT:  ((14, 16, 20), (245, 247, 250), (225, 160, 40)),
    READY:   ((10, 20, 14), (245, 247, 250), (60, 200, 120)),
    VOID:    ((30, 12, 12), (250, 220, 215), (220, 70, 60)),
    ERROR:   ((30, 20, 10), (250, 235, 215), (225, 160, 40)),
}

#: The word in the corner. Short enough to read without looking twice.
CAPTION = {
    IDLE: "READY — THROW",
    ROLLING: "ROLLING",
    READING: "READING",
    RESULT: "HANDS OFF",
    READY: "THROW AGAIN",
    VOID: "VOID",
    ERROR: "PROBLEM",
}


def _font(size: int) -> Any:
    from PIL import ImageFont

    for path in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    # Better a tiny bitmap font than no screen at all.
    return ImageFont.load_default()


def _measure(draw: Any, text: str, font: Any) -> tuple[int, int, int, int]:
    return draw.textbbox((0, 0), text, font=font)


def _fit(draw: Any, text: str, max_width: int, max_height: int, ceiling: int) -> Any:
    """
    The largest font this text fits in, by measurement rather than by arithmetic.

    Sizing from the panel's height alone looked right on a 240x240 tile and pushed the
    number straight off the edge of a 135x240 stick — the shape of the panel matters as
    much as its size, and only the renderer knows how wide a "18" actually is.
    """
    size = max(8, min(ceiling, max_height))
    while size > 8:
        font = _font(size)
        left, top, right, bottom = _measure(draw, text, font)
        if right - left <= max_width and bottom - top <= max_height:
            return font
        size -= max(1, size // 12)
    return _font(8)


def _centred(draw: Any, text: str, font: Any, width: int, y: int, fill: Any) -> int:
    left, top, right, bottom = _measure(draw, text, font)
    draw.text(((width - (right - left)) / 2 - left, y - top), text, font=font, fill=fill)
    return bottom - top


def render(presentation: Presentation, size: tuple[int, int], mono: bool = False) -> Any:
    """Draw one frame. Returns a PIL image in `1` (mono) or `RGB` mode."""
    from PIL import Image, ImageDraw

    width, height = size
    background, ink, accent = PALETTE.get(presentation.phase, PALETTE[IDLE])
    if mono:
        # On a one-bit panel the celebration is the only thing colour would have carried,
        # so it becomes the whole screen inverting.
        inverted = presentation.celebrate and presentation.anim % 2 == 1
        image = Image.new("1", size, 1 if inverted else 0)
        ink_value = 0 if inverted else 1
        draw = ImageDraw.Draw(image)
        _compose(draw, presentation, width, height, ink_value, ink_value, mono=True)
        return image

    image = Image.new("RGB", size, background)
    draw = ImageDraw.Draw(image)
    if presentation.anim and presentation.celebrate:
        _rings(draw, width, height, presentation.anim, accent)
    if presentation.anim and presentation.lament:
        # No rings for a natural 1 — the screen just goes grey and cold.
        ink = (170, 175, 185)
    _compose(draw, presentation, width, height, ink, accent, mono=False)
    return image


def _rings(draw: Any, width: int, height: int, step: int, accent: Any) -> None:
    """Expanding rings behind the number. Cheap enough to run on a Pi Zero over SPI."""
    cx, cy = width / 2, height / 2
    span = max(width, height)
    for ring in range(3):
        radius = ((step * 0.18 + ring * 0.33) % 1.0) * span * 0.75
        if radius < 4:
            continue
        fade = 1.0 - radius / (span * 0.75)
        colour = tuple(int(c * fade * 0.8) for c in accent)
        draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius],
                     outline=colour, width=max(1, int(span * 0.012)))


def _compose(draw: Any, presentation: Presentation, width: int, height: int,
             ink: Any, accent: Any, mono: bool) -> None:
    caption = CAPTION.get(presentation.phase, "")
    if presentation.celebrate and presentation.phase in (RESULT, READY):
        caption = "NICE ROLL"
    elif presentation.lament and presentation.phase in (RESULT, READY):
        caption = "OUCH"

    margin = max(2, int(width * 0.03))
    number = presentation.big
    bar = max(2, int(height * 0.04)) if presentation.phase in (VOID, RESULT, READY) else 0

    # A 128x32 OLED has no room for three stacked rows, so it gets one: the word on the
    # left, the number on the right. Anything taller keeps the readable stacked layout.
    if height < 48:
        caption_font = _fit(draw, caption, int(width * 0.62), height - 4, height)
        draw.text((margin, (height - _measure(draw, caption, caption_font)[3]) / 2),
                  caption, font=caption_font, fill=ink)
        if number is not None:
            number_font = _fit(draw, number, int(width * 0.32), height - 4, height)
            left, top, right, bottom = _measure(draw, number, number_font)
            draw.text((width - margin - (right - left) - left,
                       (height - (bottom - top)) / 2 - top), number, font=number_font, fill=ink)
        return

    caption_font = _fit(draw, caption, width - 2 * margin, int(height * 0.14),
                        max(9, int(height * 0.12)))
    draw.text((margin, max(1, int(height * 0.04))), caption,
              font=caption_font, fill=ink if mono else accent)

    top_of_body = int(height * 0.20)
    notation = ""
    if height >= 64 and presentation.notation and number is not None:
        notation = presentation.notation.split("→")[-1].strip()
        if len(notation) > 22:
            notation = notation[:21] + "…"

    notation_height = int(height * 0.16) if notation else 0
    body_height = height - top_of_body - notation_height - bar - margin

    if number is None:
        message = (presentation.message or {
            IDLE: "throw", ROLLING: "…", READING: "…", ERROR: "?",
        }.get(presentation.phase, "…"))[:18]
        font = _fit(draw, message, width - 2 * margin, body_height, int(height * 0.34))
        _centred(draw, message, font, width, top_of_body + max(0, (body_height -
                 _measure(draw, message, font)[3]) // 2), ink)
        return

    # A headline can be a word ("Full house"), so the fitter decides the size from the text
    # rather than from a digit count.
    number_font = _fit(draw, number, width - 2 * margin, body_height, int(height * 0.66))
    drawn = _measure(draw, number, number_font)
    _centred(draw, number, number_font, width,
             top_of_body + max(0, (body_height - (drawn[3] - drawn[1])) // 2), ink)

    if notation:
        font = _fit(draw, notation, width - 2 * margin, notation_height,
                    max(9, int(height * 0.14)))
        _centred(draw, notation, font, width, height - bar - notation_height, ink)

    # A bar along the bottom: the colour is the verdict, and on a mono panel its presence
    # alone says "not clean".
    if bar:
        if mono:
            if presentation.phase != READY:
                draw.rectangle([0, height - bar, width - 1, height - 1], fill=ink)
        else:
            draw.rectangle([0, height - bar, width, height], fill=accent)
