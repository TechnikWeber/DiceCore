"""The rules that decide whether a roll still counts, tested without a single pixel."""

from dicecore.dice import Box, Die
from dicecore.integrity import (
    CLEAN,
    DISTURBED,
    FAULT,
    INFO,
    UNVERIFIED,
    VOID,
    WARN,
    Event,
    compare_readings,
    decide,
    frame_hash,
    seal,
    usable,
)


def die(kind="d6", value=4, x=10, y=10, size=40) -> Die:
    return Die(kind, value, Box(x, y, size, size), 0.9)


def test_an_identical_tray_shows_no_differences():
    assert compare_readings([die(), die("d20", 14, 100)], [die(), die("d20", 14, 100)]) == []


def test_a_turned_die_is_reported_with_both_readings():
    differences = compare_readings([die(value=4)], [die(value=6)])
    assert len(differences) == 1 and "d6:4" in differences[0] and "d6:6" in differences[0]


def test_a_missing_die_is_reported_and_reads_as_english():
    differences = compare_readings([die(), die("d20", 14, 100)], [die()])
    assert "2 dice were read, 1 is on the tray now" in differences[0]


def test_an_added_die_is_reported():
    differences = compare_readings([die()], [die(), die("d6", 1, 100)])
    assert "1 die were read, 2 are on the tray now" in differences[0]


def test_a_die_nudged_without_changing_face_is_still_a_difference():
    differences = compare_readings([die(x=10)], [die(x=60)])
    assert differences and "without changing face" in differences[0]


def test_a_pixel_of_wobble_is_not_a_difference():
    # A die that has not moved still shifts a pixel or two between two frames.
    assert compare_readings([die(x=10)], [die(x=12)]) == []


def test_nothing_seen_is_a_clean_verdict():
    assert decide([], "flag") == CLEAN
    assert decide([], "void") == CLEAN


def test_the_guard_being_off_never_produces_a_verdict():
    assert decide([Event("changed", FAULT, "x")], "off") == UNVERIFIED


def test_a_reach_that_changed_nothing_is_flagged_under_every_policy():
    reach = [Event("reach", WARN, "a hand")]
    assert decide(reach, "flag") == DISTURBED
    assert decide(reach, "void") == DISTURBED  # the drink-reaching case must survive


def test_a_strict_table_voids_a_reach_as_well():
    assert decide([Event("reach", WARN, "a hand")], "void", void_on_touch=True) == VOID


def test_a_changed_reading_voids_under_void_and_flags_under_flag():
    changed = [Event("changed", FAULT, "d6:4 became d6:6")]
    assert decide(changed, "void") == VOID
    assert decide(changed, "flag") == DISTURBED


def test_only_void_stops_a_consumer_counting_the_number():
    assert usable(CLEAN) and usable(DISTURBED) and usable(UNVERIFIED)
    assert not usable(VOID)


def test_an_info_event_alone_does_not_disturb_a_roll():
    assert decide([Event("stale", INFO, "nothing moved")], "void") == CLEAN


def test_the_seal_covers_both_the_picture_and_what_was_read():
    dice = [die()]
    assert seal(b"jpeg", dice) == seal(b"jpeg", dice)
    assert seal(b"jpeg", dice) != seal(b"other", dice)
    assert seal(b"jpeg", dice) != seal(b"jpeg", [die(value=5)])
    assert seal(None, dice).startswith("sha256:")


def test_two_identical_captures_hash_identically():
    # Which is the point: a real sensor never produces the same bytes twice.
    assert frame_hash(b"x") == frame_hash(b"x") != frame_hash(b"y")
