"""
Turns, holds, chips and the Kniffel card.

The rule that shapes all of it: **holds are observed, not enforced**. DiceCore cannot stop
you picking a die up and does not try to, so nothing here may depend on a hold being right —
what gets scored is what is on the tray. The holds only tell the player and the screen what
is being kept.
"""

import pytest

from dicecore.dice import Box, Die, RollResult
from dicecore.modes.catalogue import mode_by_id, rules_for
from dicecore.play import kniffel
from dicecore.play.session import GameSession
from dicecore.play.turns import (
    TurnRules,
    apply_roll,
    detect_holds,
    end_turn,
    slots_from,
    spend_chip,
    start_turn,
    toggle_hold,
)


def d(value: int, x: int = 10, y: int = 10) -> Die:
    return Die("d6", value, Box(x, y, 40, 40), 0.95)


def hand(*values: int, spread: int = 60) -> list[Die]:
    return [d(v, 10 + i * spread) for i, v in enumerate(values)]


def result(*values: int) -> RollResult:
    return RollResult(dice=hand(*values))


KNIFFEL = TurnRules(rolls=3, holds=True, chips=2, auto_end=False)


# --- turns ------------------------------------------------------------------------


def test_a_plain_game_is_one_throw_and_done():
    rules = TurnRules()
    turn = apply_roll(start_turn(rules), hand(4, 2), rules)
    assert turn.finished and turn.rolls_left == 0


def test_kniffel_counts_three_throws_down():
    turn = start_turn(KNIFFEL)
    for expected in (2, 1, 0):
        apply_roll(turn, hand(1, 2, 3, 4, 5), KNIFFEL)
        assert turn.rolls_left == expected
    assert not turn.can_roll


def test_dice_that_did_not_move_are_recognised_as_kept():
    turn = start_turn(KNIFFEL)
    apply_roll(turn, hand(5, 5, 2, 1, 3), KNIFFEL)
    turn.dice[0].held = turn.dice[1].held = True
    # The kept two are still where they were; the other three landed elsewhere.
    again = [d(5, 10), d(5, 70), d(6, 400), d(6, 470), d(4, 540)]
    apply_roll(turn, again, KNIFFEL)
    assert [slot.held for slot in turn.dice] == [True, True, False, False, False]


def test_a_kept_die_that_changed_its_face_is_not_a_kept_die():
    # It cannot be: if the number changed, the die was thrown.
    previous = slots_from(hand(5, 5), [True, True])
    assert detect_holds(previous, [d(5, 10), d(3, 70)]) == [True, False]


def test_the_player_can_disagree_with_what_was_detected():
    turn = apply_roll(start_turn(KNIFFEL), hand(5, 5, 2), KNIFFEL)
    toggle_hold(turn, 2)
    assert turn.dice[2].held
    toggle_hold(turn, 2)
    assert not turn.dice[2].held


def test_holds_do_not_decide_what_is_scored():
    # The dice on the tray are the turn's dice, whatever the holds say — which is why a hold
    # guessed wrongly cannot cost anybody a game.
    turn = apply_roll(start_turn(KNIFFEL), hand(5, 5, 2, 1, 3), KNIFFEL)
    turn.dice[0].held = True
    apply_roll(turn, hand(6, 6, 6, 6, 6), KNIFFEL)
    assert turn.values() == [6, 6, 6, 6, 6]


# --- chips ------------------------------------------------------------------------


def test_a_chip_buys_one_more_throw_once_the_others_are_gone():
    turn = start_turn(KNIFFEL)
    for _ in range(3):
        apply_roll(turn, hand(1, 2, 3, 4, 5), KNIFFEL)
    assert turn.can_spend_chip
    turn, problem = spend_chip(turn)
    assert problem is None and turn.rolls_allowed == 4 and turn.chips_left == 1
    assert turn.can_roll


def test_a_chip_cannot_be_wasted_while_ordinary_throws_remain():
    # Spending one by fumbling a button is exactly the mistake a game should not allow.
    turn = apply_roll(start_turn(KNIFFEL), hand(1, 2), KNIFFEL)
    _, problem = spend_chip(turn)
    assert problem is not None and "no need" in problem.lower()
    assert turn.chips_left == 2


def test_chips_run_out():
    rules = TurnRules(rolls=1, holds=True, chips=1, auto_end=False)
    turn = apply_roll(start_turn(rules), hand(3), rules)
    turn, _ = spend_chip(turn)
    apply_roll(turn, hand(4), rules)
    _, problem = spend_chip(turn)
    assert problem == "No chips left."


def test_a_finished_turn_takes_no_more_throws():
    turn = end_turn(apply_roll(start_turn(KNIFFEL), hand(1, 2), KNIFFEL))
    apply_roll(turn, hand(6, 6), KNIFFEL)
    assert turn.rolls_used == 1


def test_the_number_of_chips_is_a_house_rule_not_a_game_rule():
    mode = mode_by_id("yahtzee")
    assert rules_for(mode, {"chips": 3}).chips == 3
    assert rules_for(mode, {"chips": 9}).chips == 3      # three is the ceiling
    assert rules_for(mode, None).chips == 0


# --- the scorecard ----------------------------------------------------------------


def test_every_category_scores_what_the_sheet_says():
    assert kniffel.score_for("fives", [5, 5, 1, 2, 5]) == 15
    assert kniffel.score_for("full_house", [3, 3, 3, 5, 5]) == 25
    assert kniffel.score_for("small_straight", [1, 2, 3, 4, 4]) == 30
    assert kniffel.score_for("large_straight", [2, 3, 4, 5, 6]) == 40
    assert kniffel.score_for("kniffel", [6] * 5) == 50
    assert kniffel.score_for("chance", [1, 2, 3, 4, 5]) == 15
    assert kniffel.score_for("four_of_a_kind", [4, 4, 4, 4, 2]) == 18


def test_a_category_that_is_not_made_scores_nothing():
    assert kniffel.score_for("full_house", [1, 2, 3, 4, 5]) == 0
    assert kniffel.score_for("kniffel", [6, 6, 6, 6, 1]) == 0


def test_the_upper_bonus_arrives_at_sixty_three():
    card = kniffel.Card()
    for face, category in zip(range(1, 7), kniffel.UPPER, strict=True):
        card.book(category, [face] * 5)      # three of each is exactly 63
    assert card.upper == 105 and card.bonus == 35


def test_a_category_can_only_be_booked_once():
    card = kniffel.Card()
    card.book("chance", [1, 2, 3, 4, 5])
    with pytest.raises(ValueError, match="already booked"):
        card.book("chance", [6, 6, 6, 6, 6])


def test_a_box_can_be_crossed_out_for_nothing():
    card = kniffel.Card()
    card.book("kniffel", [1, 2, 3, 4, 5], cross_out=True)
    assert card.scores["kniffel"] == 0 and "kniffel" not in card.open_categories()


def test_a_card_knows_when_it_is_full():
    card = kniffel.Card()
    for category in kniffel.CATEGORIES:
        card.book(category, [1, 1, 1, 1, 1], cross_out=True)
    assert card.complete and card.total == 0


# --- the live game ----------------------------------------------------------------


def game(**kwargs) -> GameSession:
    return GameSession("yahtzee", KNIFFEL, kwargs.get("players", ["A", "B"]))


def test_a_throw_advances_the_turn_and_a_stale_reading_does_not():
    session = game()
    assert session.observe(result(1, 2, 3, 4, 5))
    stale = result(1, 2, 3, 4, 5)
    stale.stale = True
    assert not session.observe(stale)
    assert session.turn.rolls_used == 1


def test_a_throw_with_no_dice_is_not_a_throw():
    session = game()
    assert not session.observe(RollResult())


def test_booking_scores_the_card_and_hands_the_tower_on():
    session = game()
    session.observe(result(3, 3, 3, 5, 5))
    outcome = session.book("full_house")
    assert outcome["points"] == 25
    assert session.cards[0].total == 25
    assert session.turn.player == 1 and session.turn.number == 2
    assert session.turn.rolls_used == 0


def test_a_category_worth_nothing_has_to_be_given_up_deliberately():
    session = game()
    session.observe(result(1, 2, 3, 4, 5))
    with pytest.raises(ValueError, match="cross_out"):
        session.book("kniffel")
    assert session.book("kniffel", cross_out=True)["points"] == 0


def test_throwing_again_with_no_throws_left_is_refused_and_explained():
    session = game()
    for _ in range(3):
        session.observe(result(1, 2, 3, 4, 5))
    assert not session.observe(result(6, 6, 6, 6, 6))
    assert "chip" in session.message


def test_the_turn_keeps_its_own_reading():
    # Once the throws are gone the tray is still watched, and the newest reading is about
    # dice this turn never rolled. The screen must not put that headline over these dice.
    session = game()
    rolled = result(3, 3, 3, 5, 5)
    rolled.reading = {"headline": "Full house"}
    session.observe(rolled)
    later = result(6, 6, 6, 6, 6)
    later.reading = {"headline": "Yahtzee"}
    for _ in range(4):
        session.observe(later)
    assert session.turn.values() == [6, 6, 6, 6, 6]      # throws two and three counted
    assert session.reading["headline"] == "Yahtzee"      # and it is *their* reading


def test_the_log_remembers_what_was_booked():
    session = game()
    session.observe(result(2, 2, 2, 5, 5))
    session.book("full_house")
    entry = session.to_json()["log"][0]
    assert entry["booked"] == "full_house" and entry["points"] == 25


def test_changing_the_players_starts_a_new_game():
    session = game()
    session.observe(result(3, 3, 3, 5, 5))
    session.book("full_house")
    session.configure("yahtzee", KNIFFEL, ["A", "B", "C"])
    assert all(card.total == 0 for card in session.cards)
    assert len(session.cards) == 3 and session.turn.number == 1


def test_a_game_without_a_scorecard_still_counts_turns():
    session = GameSession("normal", TurnRules(), ["A"])
    session.observe(result(4, 2))
    assert not session.cards
    session.finish_turn("6")
    assert session.turn.number == 2 and session.to_json()["log"][0]["headline"] == "6"


def test_the_winner_is_only_named_when_there_is_one():
    cards = [kniffel.Card("A"), kniffel.Card("B")]
    assert kniffel.leader(cards) is None          # nobody has scored: a tie
    cards[1].book("chance", [6, 6, 6, 6, 6])
    assert kniffel.leader(cards) == 1
