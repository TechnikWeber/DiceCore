"""
Naming a die's colour.

The classification is a pure function of hue, saturation and value, so what counts as "red"
is a question that can be answered without a photograph. The sampling is checked against
rendered dice, which is the only honest way to test "does it find the body colour and not
the pips".
"""

import pytest

from dicecore.engine.colour import BANDS, NAMES, classify, swatch


def test_brightness_is_decided_before_hue():
    # A black die under a warm lamp has a perfectly confident hue and it means nothing.
    assert classify(20, 200, 20) == "black"
    assert classify(120, 200, 10) == "black"


def test_an_unsaturated_sample_is_white_or_grey_never_a_colour():
    assert classify(5, 10, 230) == "white"
    assert classify(5, 10, 110) == "grey"


def test_the_named_colours_land_where_they_should():
    assert classify(3, 200, 180) == "red"
    assert classify(15, 200, 180) == "orange"
    assert classify(28, 220, 220) == "yellow"
    assert classify(60, 180, 150) == "green"
    assert classify(92, 190, 170) == "cyan"
    assert classify(115, 200, 180) == "blue"
    assert classify(140, 180, 160) == "purple"
    assert classify(160, 180, 160) == "pink"


def test_red_is_found_at_both_ends_of_the_scale():
    # Hue is a circle and red sits across the seam; missing that half turns red into pink.
    assert classify(2, 200, 180) == "red"
    assert classify(176, 200, 180) == "red"


def test_the_bands_cover_the_whole_circle_without_a_gap():
    edges = sorted((low, high) for low, high, _ in BANDS)
    assert edges[0][0] == 0 and edges[-1][1] == 180
    for (_, end), (start, _) in zip(edges, edges[1:], strict=False):
        assert end == start, f"gap or overlap at {end}"


def test_every_name_has_a_swatch_to_draw_it_with():
    for name in NAMES:
        assert swatch(name).startswith("#") and len(swatch(name)) == 7


# --- against rendered dice --------------------------------------------------------

pytest.importorskip("cv2")

from dicecore.config import Settings  # noqa: E402
from dicecore.dice import Frame  # noqa: E402
from dicecore.engine.classic import ClassicEngine  # noqa: E402
from dicecore.synth import render_scene  # noqa: E402


def read(body, ink, tray=(35, 40, 45), light=True, dark_pips=True):
    settings = Settings()
    settings.classic.detect_colour = True
    settings.classic.dice_are_light = light
    settings.classic.pips_are_dark = dark_pips
    image, _ = render_scene([("d6", 5)], seed=3, width=400, height=300, die_px=90,
                            tray_bgr=tray, body_bgr=body, ink_bgr=ink)
    return ClassicEngine(settings).read(Frame(image=image))


def test_a_coloured_die_is_named_and_still_counted():
    for name, body in (("red", (60, 60, 220)), ("blue", (230, 120, 70)),
                       ("green", (110, 200, 90)), ("yellow", (60, 210, 240))):
        result = read(body, (250, 250, 250) if name in ("red", "blue") else (25, 25, 30),
                      dark_pips=name not in ("red", "blue"))
        assert result.dice, name
        assert result.dice[0].colour == name, name
        assert result.dice[0].value == 5, name


def test_a_black_die_with_white_pips_reads_on_a_light_tray():
    # Which is the only way it can be set up: a black die on a dark tray is invisible to a
    # camera and to a person, and no engine can be blamed for that.
    result = read((45, 45, 50), (240, 240, 240), tray=(225, 228, 232),
                  light=False, dark_pips=False)
    assert result.dice[0].colour == "black" and result.dice[0].value == 5


def test_the_pips_do_not_drag_the_colour_towards_grey():
    # The body is always more than half the pixels, so the median lands on it. An earlier
    # version trimmed the darkest quarter first, which is exactly wrong for a dark die.
    assert read((60, 60, 220), (25, 25, 30)).dice[0].colour == "red"


def test_colour_is_not_looked_at_unless_it_was_asked_for():
    settings = Settings()
    assert settings.classic.detect_colour is False
    image, _ = render_scene([("d6", 5)], seed=3, width=400, height=300, die_px=90,
                            body_bgr=(60, 60, 220))
    result = ClassicEngine(settings).read(Frame(image=image))
    assert result.dice[0].colour is None
