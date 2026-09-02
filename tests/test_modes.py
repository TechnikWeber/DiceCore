"""
Game modes: the same faces, read the way each game reads them.

Every rule here is a pure function, which is the point of the design — "does a full house
score 25" is a question that should be answerable without a camera, a display or a server.
"""


from dicecore.dice import Box, Die
from dicecore.modes import ModeSession, expected_count, interpret
from dicecore.modes.catalogue import MODES, mode_by_id
from dicecore.modes.fairness import Tally
from dicecore.modes.scoring import farkle_score, percentile_value, yahtzee_combination


def d(kind: str, value: int) -> Die:
    return Die(kind, value, Box(0, 0, 40, 40), 0.95)


def unread(kind: str = "d20") -> Die:
    return Die(kind, 0, Box(0, 0, 40, 40), 0.0)


def head(dice, mode="normal", **params):
    return interpret(dice, mode, params or None).headline


# --- the catalogue ----------------------------------------------------------------


def test_every_mode_names_dice_it_can_actually_read():
    from dicecore.dice import DIE_KINDS

    for mode in MODES:
        assert mode.kinds, mode.id
        assert set(mode.kinds) <= set(DIE_KINDS), mode.id
        assert mode.blurb.endswith("."), mode.id


def test_every_mode_dispatches_to_a_rule_that_exists():
    for mode in MODES:
        score = interpret([d("d6", 3), d("d6", 4)], mode.id)
        assert score.headline, mode.id


def test_the_expected_dice_count_is_readable_by_both_people_and_code():
    assert expected_count("2") == (2, 2)
    assert expected_count("1–6") == (1, 6)
    assert expected_count("any") is None


# --- the three the project started from -------------------------------------------


def test_normal_adds_up_pips():
    assert head([d("d6", 4), d("d6", 3), d("d6", 6)]) == "13"


def test_normal_extended_counts_a_ten_sided_zero_as_ten():
    # The d10's oldest argument, settled per mode rather than per die.
    assert head([d("d6", 4), d("d10", 0)], "normal_extended") == "14"


def test_a_ten_sided_zero_is_a_face_not_a_missing_die():
    score = interpret([d("d10", 0)], "normal_extended")
    assert not any("could not be read" in w for w in score.warnings)


def test_an_unread_die_is_left_out_and_said_out_loud():
    score = interpret([d("d6", 4), unread()], "normal")
    assert score.value == 4
    assert any("could not be read" in w for w in score.warnings)


def test_roleplaying_calls_out_the_two_faces_everyone_reacts_to():
    assert "critical" in head([d("d20", 20)], "rpg")
    assert "fumble" in head([d("d20", 1)], "rpg")
    assert interpret([d("d20", 20)], "rpg").celebrate
    assert interpret([d("d20", 1)], "rpg").lament


def test_roleplaying_reads_a_percentile_pair_as_one_number():
    assert head([d("d100", 40), d("d10", 3)], "rpg") == "43"
    assert percentile_value([d("d100", 0), d("d10", 0)]) == 100     # the best possible roll
    assert percentile_value([d("d100", 0), d("d10", 1)]) == 1
    assert percentile_value([d("d6", 3)]) is None


def test_roleplaying_still_just_adds_up_a_handful_of_damage_dice():
    assert head([d("d6", 4), d("d6", 5), d("d8", 7)], "rpg") == "16"


# --- the family of games one mode covers ------------------------------------------


def test_a_pool_counts_the_dice_that_reached_the_target():
    assert head([d("d6", 5), d("d6", 6), d("d6", 2), d("d6", 4)], "pool", threshold=4) \
        == "3 successes"
    assert head([d("d6", 1)], "pool", threshold=4) == "0 successes"


def test_one_success_is_not_pluralised():
    assert head([d("d6", 5), d("d6", 1)], "pool", threshold=4) == "1 success"


def test_a_pool_can_count_the_top_face_twice():
    # World of Darkness and friends: a ten counts for two successes.
    assert head([d("d10", 9), d("d10", 8)], "pool", threshold=8, double_on_max=True) \
        == "3 successes"


def test_best_of_takes_the_highest_and_says_what_it_beat():
    score = interpret([d("d20", 7), d("d20", 18)], "best", {"take": "high"})
    assert score.headline == "18" and "7" in score.detail


def test_worst_of_is_the_same_mode_the_other_way_round():
    assert head([d("d20", 7), d("d20", 18)], "best", take="low") == "7"


def test_rolling_under_a_target_says_whether_it_was_made():
    assert "success" in head([d("d100", 40), d("d10", 3)], "under", target=55, percentile=True)
    assert "failure" in head([d("d100", 70), d("d10", 1)], "under", target=55, percentile=True)


# --- games ------------------------------------------------------------------------


def test_yahtzee_finds_the_best_combination():
    assert yahtzee_combination([3, 3, 3, 5, 5]) == ("full house", 25)
    assert yahtzee_combination([4, 4, 4, 4, 4]) == ("yahtzee", 50)
    assert yahtzee_combination([1, 2, 3, 4, 5]) == ("large straight", 40)
    assert yahtzee_combination([2, 3, 4, 5, 5]) == ("small straight", 30)
    assert yahtzee_combination([6, 6, 6, 6, 2]) == ("four of a kind", 26)
    assert yahtzee_combination([1, 2, 3, 5, 6]) == ("chance", 17)


def test_a_small_straight_does_not_care_about_the_fifth_die():
    assert yahtzee_combination([3, 4, 5, 6, 6])[0] == "small straight"


def test_farkle_scores_ones_fives_and_sets():
    assert farkle_score([1, 1, 1, 5, 2, 3])[0] == 1050        # three ones plus a five
    assert farkle_score([1, 2, 3, 4, 5, 6])[0] == 1500        # a straight
    assert farkle_score([2, 2, 4, 4, 6, 6])[0] == 1500        # three pairs
    assert farkle_score([6, 6, 6, 6])[0] == 1200              # four of a kind doubles
    assert farkle_score([2, 3, 4, 6])[0] == 0                 # a Farkle


def test_a_farkle_is_announced_as_such():
    score = interpret([d("d6", v) for v in (2, 3, 4, 6)], "farkle")
    assert score.headline == "Farkle!" and score.lament


def test_backgammon_knows_a_double_is_four_moves():
    score = interpret([d("d6", 4), d("d6", 4)], "backgammon")
    assert score.headline == "double 4" and score.extras["moves"] == [4, 4, 4, 4]
    assert interpret([d("d6", 5), d("d6", 3)], "backgammon").headline == "5-3"


def test_maexchen_reads_two_dice_as_one_number():
    assert head([d("d6", 6), d("d6", 5)], "maexchen") == "65"
    assert head([d("d6", 1), d("d6", 2)], "maexchen") == "Mäxchen!"
    assert head([d("d6", 3), d("d6", 3)], "maexchen") == "double 3"


def test_the_counting_mode_shows_one_die_and_celebrates_every_throw():
    score = interpret([d("d6", 3)], "counting")
    assert score.headline == "3" and score.celebrate


# --- modes with memory ------------------------------------------------------------


def test_an_exploding_roll_stays_open_until_a_die_lands_short():
    session = ModeSession()
    first = interpret([d("d8", 8)], "exploding", session=session)
    assert first.headline == "8…" and first.extras["open"]
    second = interpret([d("d8", 8)], "exploding", session=session)
    assert second.headline == "16…"
    third = interpret([d("d8", 3)], "exploding", session=session)
    assert third.headline == "19" and not third.extras["open"]
    # And the next throw starts from nothing again.
    assert interpret([d("d8", 2)], "exploding", session=session).headline == "2"


def test_switching_mode_clears_what_the_previous_one_remembered():
    session = ModeSession()
    interpret([d("d8", 8)], "exploding", session=session)
    interpret([d("d6", 3)], "normal", session=session)
    assert session.carried == 0


def test_the_fairness_test_says_nothing_until_it_has_enough_throws():
    tally = Tally("d6")
    for value in (1, 2, 3, 4, 5):
        tally.observe(value)
    verdict = tally.verdict()
    assert verdict["state"] == "not enough" and "30" in verdict["wording"]


def test_a_flat_distribution_reads_as_nothing_unusual():
    tally = Tally("d6")
    for _ in range(50):
        for value in range(1, 7):
            tally.observe(value)
    assert tally.verdict()["state"] == "nothing unusual"


def test_a_die_that_favours_one_face_is_flagged():
    tally = Tally("d6")
    for index in range(300):
        tally.observe(6 if index % 3 == 0 else (index % 6) + 1)
    verdict = tally.verdict()
    assert verdict["state"] in ("unusual", "very unusual")
    assert verdict["most_common"] == 6


def test_the_fairness_test_never_claims_a_die_is_fair():
    # It cannot. Saying so plainly is the whole reason the wording is written out.
    tally = Tally("d20")
    for _ in range(10):
        for value in range(1, 21):
            tally.observe(value)
    assert "not the same as showing it is fair" in tally.verdict()["wording"]


def test_a_ten_sided_die_is_tested_against_the_faces_it_actually_has():
    assert len(Tally("d10", d10_style="0-9").faces()) == 10
    assert Tally("d10", d10_style="1-10").faces()[0] == 1


# --- guardrails -------------------------------------------------------------------


def test_a_mode_says_when_the_tray_does_not_match_it():
    score = interpret([d("d6", 3), d("d6", 3), d("d6", 1)], "backgammon")
    assert any("2 dice" in w and "3 on the tray" in w for w in score.warnings)


def test_a_mode_says_when_a_die_does_not_belong_to_it():
    score = interpret([d("d6", 3), d("d20", 11)], "normal")
    assert any("not part of" in w for w in score.warnings)


def test_only_one_complaint_per_problem():
    # Two sentences saying "there are three dice" is one sentence too many.
    score = interpret([d("d6", 3), d("d6", 3), d("d6", 1)], "maexchen")
    assert len([w for w in score.warnings if "on the tray" in w]) == 1


def test_the_build_your_own_mode_takes_its_rule_from_the_settings():
    dice = [d("d6", 5), d("d6", 6), d("d6", 2)]
    assert interpret(dice, "custom", {"rule": "sum"}).headline == "13"
    assert interpret(dice, "custom", {"rule": "pool", "threshold": 5}).headline == "2 successes"
    assert interpret(dice, "custom", {"rule": "best", "take": "low"}).headline == "2"


def test_an_unknown_mode_falls_back_instead_of_failing():
    assert interpret([d("d6", 4)], "nonsense").headline == "4"


def test_a_parameter_a_mode_does_not_have_is_ignored():
    assert mode_by_id("normal") is not None
    assert interpret([d("d6", 4)], "normal", {"threshold": 99}).headline == "4"


def test_a_pool_celebrates_in_proportion_to_the_pool():
    # With three dice, every one succeeding is the best result there is — and under a fixed
    # threshold of four successes it was never worth a sound.
    for count in (2, 3, 5, 8):
        best = [d("d6", 6)] * count
        assert interpret(best, "pool", {"threshold": 4}).celebrate, count


def test_a_half_hearted_pool_does_not_celebrate():
    dice = [d("d6", 6), d("d6", 1), d("d6", 1), d("d6", 1), d("d6", 1), d("d6", 1)]
    assert not interpret(dice, "pool", {"threshold": 4}).celebrate


def test_a_model_can_be_trained_from_several_sets_at_once(tmp_path):
    # The case it exists for: you collect your six-siders and a friend collects his d20s.
    from dicecore.dataset import DatasetStore
    from dicecore.dice import Box as B
    from dicecore.dice import Die as D
    from dicecore.dice import RollResult
    from dicecore.training.data import readiness

    store = DatasetStore(tmp_path)
    mine = store.create_set("my d6")
    his = store.create_set("his d20")
    for record, kind, values in ((mine, "d6", range(1, 7)), (his, "d20", range(1, 21))):
        for value in values:
            sample = store.add_sample(record.id, b"jpeg", RollResult(
                dice=[D(kind, 0, B(0, 0, 30, 30), confidence=0.0)]))
            store.update_sample(record.id, sample.id, [{"kind": kind, "value": value}])

    assert len(readiness(store, mine.id).classes) == 6
    assert len(readiness(store, [mine.id, his.id]).classes) == 26
