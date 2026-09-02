"""
The screen and the lamps.

The rule they exist to enforce: whatever is on the panel and whatever the LEDs are doing
must be derived from one state, so they can never disagree about whose turn it is.
"""

import time

import pytest

from dicecore.config import PanelSettings, SignalSettings
from dicecore.dice import Box, Die, RollResult
from dicecore.panel import OutputHub
from dicecore.panel.signals import SignalOutput
from dicecore.panel.state import (
    ERROR,
    IDLE,
    READING,
    READY,
    RESULT,
    ROLLING,
    VOID,
    Presentation,
    is_celebration,
    is_lament,
    presentation_for,
)


def roll(*dice: tuple[str, int]) -> RollResult:
    return RollResult(dice=[Die(kind, value, Box(0, 0, 40, 40), 0.9) for kind, value in dice])


def unread(kind: str) -> Die:
    """A die the engine found but could not read: no value *and* no confidence."""
    return Die(kind, 0, Box(0, 0, 40, 40), 0.0)


# --- what the state says ----------------------------------------------------------


def test_green_means_throw_and_nothing_else_does():
    assert Presentation(phase=IDLE).go and Presentation(phase=READY).go
    for phase in (ROLLING, READING, RESULT, VOID, ERROR):
        assert not Presentation(phase=phase).go, phase


def test_the_number_is_still_shown_while_the_tray_is_watched():
    # The result phase is "hands off", not "no number" — the whole point is that the number
    # is public the moment it is read.
    presentation = presentation_for(roll(("d6", 4)), RESULT)
    assert presentation.total == 4 and presentation.busy


def test_a_natural_maximum_is_a_celebration():
    assert is_celebration(roll(("d20", 20)), "max_die", 18)
    assert is_celebration(roll(("d6", 6), ("d20", 3)), "max_die", 18)
    assert not is_celebration(roll(("d20", 19)), "max_die", 18)


def test_a_total_threshold_is_the_other_way_to_celebrate():
    assert is_celebration(roll(("d6", 6), ("d6", 6), ("d6", 6)), "total", 18)
    assert not is_celebration(roll(("d6", 6), ("d6", 6), ("d6", 5)), "total", 18)


def test_a_die_that_could_not_be_read_never_celebrates():
    # A party over a number the machine could not read is worse than silence.
    good = roll(("d20", 20))
    good.dice.append(unread("d20"))
    assert not is_celebration(good, "max_die", 18)
    bad = roll(("d20", 1))
    bad.dice.append(unread("d20"))
    assert not is_lament(bad, True)


def test_a_d10_showing_zero_does_not_block_a_celebration():
    # It is a face, not a failure — see Die.unread.
    assert is_celebration(roll(("d20", 20), ("d10", 0)), "max_die", 18)


def test_celebration_can_be_switched_off():
    assert not is_celebration(roll(("d20", 20)), "off", 18)


def test_a_natural_one_is_marked_separately():
    assert is_lament(roll(("d20", 1)), True)
    assert not is_lament(roll(("d20", 2)), True)
    assert not is_lament(roll(("d20", 1)), False)


def test_a_d10_showing_zero_is_not_a_natural_one():
    # A d10 counts from 0, so its lowest face is 0 and its "1" is unremarkable.
    assert not is_lament(roll(("d10", 1)), True)


# --- the lamps --------------------------------------------------------------------


def signals(**overrides) -> SignalOutput:
    settings = SignalSettings(enabled=True, beep_ms=1)
    for key, value in overrides.items():
        setattr(settings, key, value)
    return SignalOutput(settings)


def test_the_lamps_follow_the_phase():
    lamps = signals()
    lamps.present(Presentation(phase=IDLE))
    assert lamps.green.state and not lamps.red.state
    lamps.present(Presentation(phase=RESULT, total=4))
    assert not lamps.green.state and lamps.red.state
    lamps.present(Presentation(phase=READY, total=4))
    assert lamps.green.state and not lamps.red.state
    lamps.close()


def test_the_buzzer_marks_the_number_and_the_turn():
    lamps = signals()
    lamps.present(Presentation(phase=RESULT, total=4))
    assert lamps.last_sound == "result"
    lamps.present(Presentation(phase=READY, total=4))
    assert lamps.last_sound == "your turn"
    lamps.present(Presentation(phase=VOID, total=4))
    assert lamps.last_sound == "void"
    lamps.close()


def test_a_great_roll_and_an_awful_one_sound_different():
    lamps = signals()
    lamps.present(Presentation(phase=RESULT, total=20, celebrate=True))
    assert lamps.last_sound == "nice roll"
    lamps.present(Presentation(phase=IDLE))
    lamps.present(Presentation(phase=RESULT, total=1, lament=True))
    assert lamps.last_sound == "ouch"
    lamps.close()


def test_the_sound_fires_once_per_phase_not_once_per_frame():
    lamps = signals()
    lamps.present(Presentation(phase=RESULT, total=4))
    lamps.last_sound = ""
    for _ in range(5):
        lamps.present(Presentation(phase=RESULT, total=4))
    assert lamps.last_sound == ""       # nothing new happened, so nothing beeped
    lamps.close()


def test_a_pin_set_to_minus_one_is_simply_left_out():
    lamps = signals(buzzer_pin=-1)
    lamps.present(Presentation(phase=RESULT, total=4))
    assert lamps.buzzer.number == -1
    lamps.close()


def test_the_lamps_are_simulated_when_there_is_no_gpio(monkeypatch):
    # Which is what makes the web UI usable before anything is soldered.
    lamps = signals()
    described = lamps.describe()
    assert "green" in described and "pin" in described["green"]
    lamps.close()


# --- the display ------------------------------------------------------------------


def test_a_display_renders_a_preview_without_any_hardware():
    pytest.importorskip("PIL")
    settings = PanelSettings()
    settings.display.enabled = True
    hub = OutputHub(settings)
    try:
        hub.update(presentation_for(roll(("d6", 4), ("d20", 14)), RESULT))
        for _ in range(50):
            if hub.display.last_png:
                break
            time.sleep(0.02)
        assert hub.display.last_png.startswith(b"\x89PNG")
        assert hub.display.describe()["attached"] is False
    finally:
        hub.close()


def test_every_panel_renders_at_its_own_size():
    from dicecore.panel.displays import COMMON_SIZES
    from dicecore.panel.render import render

    pytest.importorskip("PIL")
    for kind, sizes in COMMON_SIZES.items():
        for size in sizes:
            image = render(Presentation(phase=RESULT, total=118,
                                        notation="3d20 → 4, 14, 100"),
                           size, mono=kind.startswith("ssd1306"))
            assert image.size == size, (kind, size)


def test_a_hub_with_nothing_enabled_costs_nothing():
    hub = OutputHub(PanelSettings())
    assert not hub.enabled and hub.devices == []
    hub.update(Presentation(phase=RESULT, total=4))     # must not raise, must not start a thread
    hub.close()


def test_the_hub_shows_the_newest_state_even_when_it_falls_behind():
    pytest.importorskip("PIL")
    settings = PanelSettings()
    settings.display.enabled = True
    hub = OutputHub(settings)
    try:
        for total in range(30):
            hub.update(Presentation(phase=RESULT, total=total))
        for _ in range(50):
            if hub.latest.total == 29:
                break
            time.sleep(0.02)
        assert hub.latest.total == 29
    finally:
        hub.close()


# --- what is worth celebrating has to scale with the tray -------------------------


def test_a_perfect_throw_celebrates_however_many_dice_there_are():
    # A fixed total cannot be right for two tables at once: 18 is impossible with two
    # six-siders and unremarkable with six, so a threshold of 18 meant a perfect 2d6 never
    # celebrated at all.
    for count in (1, 2, 3, 5, 6):
        assert is_celebration(roll(*[("d6", 6)] * count), "near_max", 0), count


def test_a_middling_throw_does_not_celebrate_at_any_count():
    for count in (2, 3, 5, 6):
        assert not is_celebration(roll(*[("d6", 3)] * count), "near_max", 0), count


def test_near_max_understands_dice_that_are_not_six_siders():
    assert is_celebration(roll(("d20", 20)), "near_max", 0)
    assert not is_celebration(roll(("d20", 11)), "near_max", 0)
    assert is_celebration(roll(("d20", 19), ("d6", 6)), "near_max", 0)


def test_an_absolute_total_is_still_available_for_those_who_want_it():
    assert is_celebration(roll(("d6", 6), ("d6", 6), ("d6", 6)), "total", 18)
    assert not is_celebration(roll(("d6", 6), ("d6", 6)), "total", 18)


def test_the_best_possible_total_is_what_near_max_measures_against():
    from dicecore.dice import best_total

    assert best_total(["d6", "d6"]) == 12
    assert best_total(["d20", "d6"]) == 26
    assert best_total([]) == 0
