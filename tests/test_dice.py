from dicecore.dice import Box, Die, RollResult, is_valid, values_for


def box() -> Box:
    return Box(0, 0, 10, 10)


def test_d10_counts_from_zero_and_d100_in_tens():
    assert values_for("d10")[0] == 0
    assert values_for("d100") == [0, 10, 20, 30, 40, 50, 60, 70, 80, 90]
    assert values_for("d20")[-1] == 20


def test_validity_follows_the_kind():
    assert is_valid("d20", 20) and not is_valid("d6", 20)
    assert not is_valid("d13", 1)


def test_notation_groups_by_kind_and_lists_values_in_the_same_order():
    result = RollResult(dice=[Die("d20", 14, box()), Die("d6", 4, box()), Die("d20", 3, box())])
    assert result.notation == "1d6+2d20 → 4, 14, 3"
    assert result.total == 21


def test_an_unread_die_is_a_question_mark_never_a_zero():
    # A consumer would happily add a 0 into a total; a "?" makes it look before it leaps.
    result = RollResult(dice=[Die("d20", 0, box(), confidence=0.0), Die("d6", 4, box())])
    assert result.notation.split("→")[1].strip() == "4, ?"
    assert result.to_json()["dice"][0]["unread"] is True     # the d20
    assert result.to_json()["dice"][1]["unread"] is False    # the d6


def test_a_d10_showing_zero_is_a_face_not_a_failure():
    # The distinction that `value == 0` alone cannot make: a d10 printed 0-9 has a zero
    # face, and reading it as "could not read" dropped it out of every sum.
    zero = Die("d10", 0, box(), confidence=0.95)
    assert not zero.unread
    assert RollResult(dice=[zero]).notation.endswith("→ 0")
    assert Die("d10", 0, box(), confidence=0.0).unread


def test_empty_result_says_so():
    assert RollResult().notation == "no dice"
    assert RollResult().total == 0


def test_the_small_dice_a_roleplaying_table_owns_are_in_the_vocabulary():
    # A d3 is a real die, even though most tables read one off a d6; a d2 turns up with it.
    assert values_for("d3") == [1, 2, 3]
    assert values_for("d2") == [1, 2]
    assert is_valid("d3", 3) and not is_valid("d3", 4)


def test_the_whole_roleplaying_set_is_known():
    from dicecore.dice import DIE_KINDS

    assert {"d4", "d6", "d8", "d10", "d100", "d12", "d20"} <= set(DIE_KINDS)
