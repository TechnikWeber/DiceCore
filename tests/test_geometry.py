from dicecore.dice import Box
from dicecore.engine.geometry import (
    kind_from_size,
    offset,
    overlaps,
    pip_confidence,
    plausible_die,
    roi_box,
    sort_reading_order,
)


def test_a_die_candidate_has_to_be_the_right_size_and_roughly_square():
    frame = 1000 * 1000
    assert plausible_die(Box(0, 0, 100, 100), frame, 0.0015, 0.08, 0.6, 1.7)
    assert not plausible_die(Box(0, 0, 5, 5), frame, 0.0015, 0.08, 0.6, 1.7)      # a crumb
    assert not plausible_die(Box(0, 0, 900, 900), frame, 0.0015, 0.08, 0.6, 1.7)  # the tray
    assert not plausible_die(Box(0, 0, 200, 40), frame, 0.0015, 0.08, 0.6, 1.7)   # a shadow


def test_the_tray_is_stored_as_fractions_so_it_survives_a_resolution_change():
    assert roi_box(1280, 720, 0.25, 0.5, 0.5, 0.5) == Box(320, 360, 640, 360)
    assert roi_box(640, 360, 0.25, 0.5, 0.5, 0.5) == Box(160, 180, 320, 180)


def test_the_tray_is_clamped_to_the_frame():
    clamped = roi_box(100, 100, 0.9, 0.9, 0.5, 0.5)
    assert clamped.x + clamped.w <= 100 and clamped.y + clamped.h <= 100


def test_uniform_pips_are_trusted_more_than_a_mixed_bag():
    tight = pip_confidence(5, [100, 101, 99, 100, 100])
    loose = pip_confidence(5, [100, 40, 99, 100, 100])
    assert tight > loose > 0


def test_an_impossible_pip_count_has_no_confidence_at_all():
    assert pip_confidence(0, []) == 0.0
    assert pip_confidence(7, [10] * 7) == 0.0


def test_reading_order_is_stable_across_a_row_boundary():
    # Two dice at y=8 and y=10 are one row; bucketing by y // height would split them.
    boxes = [Box(50, 50, 20, 20), Box(10, 10, 20, 20), Box(60, 8, 20, 20)]
    assert sort_reading_order(boxes) == [1, 2, 0]
    assert sort_reading_order([]) == []


def test_duplicate_contours_of_one_die_are_recognised_as_overlapping():
    assert overlaps(Box(0, 0, 40, 40), Box(4, 4, 40, 40))
    assert not overlaps(Box(0, 0, 40, 40), Box(60, 60, 40, 40))


def test_size_is_only_a_hint_and_stays_silent_without_calibration():
    assert kind_from_size(Box(0, 0, 40, 40), 0.0) is None
    assert kind_from_size(Box(0, 0, 40, 40), 0.5) == "d20"


def test_offset_moves_a_box_back_into_full_frame_coordinates():
    assert offset(Box(5, 5, 10, 10), 100, 200) == Box(105, 205, 10, 10)


def test_the_dice_a_table_says_are_in_play_name_an_unread_die():
    # "Which dice may appear" was a checkbox list that changed nothing at all. A control
    # that does nothing is worse than no control.
    from dicecore.engine.geometry import guess_unread_kind

    box = Box(0, 0, 80, 80)
    assert guess_unread_kind(box, 0, ["d6", "d12"]) == "d12"
    assert guess_unread_kind(box, 0, ["d6", "d20"]) == "d20"


def test_size_decides_when_the_table_named_several_numeral_dice():
    from dicecore.engine.geometry import guess_unread_kind

    # A calibrated tray can tell them apart; without one, the first named kind is the guess.
    assert guess_unread_kind(Box(0, 0, 80, 80), 0.25, ["d6", "d12", "d20"]) == "d20"
    assert guess_unread_kind(Box(0, 0, 80, 80), 0, ["d6", "d12", "d20"]) == "d12"


def test_a_table_that_named_only_pipped_dice_still_gets_an_answer():
    from dicecore.engine.geometry import guess_unread_kind

    assert guess_unread_kind(Box(0, 0, 80, 80), 0, ["d6"]) == "d20"
