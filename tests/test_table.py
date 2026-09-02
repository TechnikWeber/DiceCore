"""
Playing one game across several DiceCores.

The rule this file exists for is **only the player whose turn it is may act**. It is the one
thing a turn-based game played in three rooms at once can get wrong in a way nobody notices
until a scorecard box has already been filled in by the wrong person.

`protocol` is pure on purpose, so most of that can be decided here without a socket.
"""

import pytest

from dicecore.table import protocol
from dicecore.table.protocol import Seat


def action(name, seat=0, current=0, running=True):
    return protocol.check(protocol.action(name), seat, current, running)


def test_the_player_whose_turn_it_is_may_act():
    assert action("book", seat=1, current=1) is None


def test_nobody_else_may():
    assert action("book", seat=1, current=0) == "It is not your turn."
    assert action("roll", seat=0, current=1) == "It is not your turn."


def test_a_guest_without_a_seat_is_told_so():
    assert action("roll", seat=None) == "You have no seat at this table yet."


def test_actions_that_are_nobody_particular_s_are_always_allowed():
    # Leaving must work while somebody else is throwing, or a guest who closes the tab
    # during another player's turn stays at the table forever.
    assert action("leave", seat=1, current=0) is None
    assert action("ping", seat=None) is None


def test_acting_before_the_game_starts_is_refused():
    assert action("roll", seat=0, current=0, running=False) == "No game is running."


def test_an_unknown_action_is_named_rather_than_ignored():
    assert "wibble" in (protocol.check({"type": "action", "action": "wibble"}, 0, 0, True) or "")


def test_state_messages_are_not_permission_checked():
    # Only actions are decided here. A host sending state to a guest is not asking for
    # anything, and running it through the turn rule would refuse the game itself.
    assert protocol.check(protocol.state({}, [], None), None, 0, False) is None


def test_rubbish_is_refused_rather_than_crashing():
    assert protocol.check("not a message", 0, 0, True) == "That is not a message."


def test_a_different_protocol_version_is_explained():
    assert protocol.version_problem(protocol.VERSION) is None
    problem = protocol.version_problem(protocol.VERSION + 1)
    assert "Update the older one" in problem
    assert "did not say" in protocol.version_problem(None)


def test_a_seat_survives_the_round_trip():
    seat = Seat("Bob", 1, remote=True)
    assert seat.to_json()["name"] == "Bob"
    assert seat.to_json()["connected"] is True


# --- the host, with a real reader behind it -----------------------------------------

pytest.importorskip("cv2")

from dicecore.config import Settings  # noqa: E402
from dicecore.play.turns import TurnRules  # noqa: E402
from dicecore.reader import Reader  # noqa: E402
from dicecore.table import Table  # noqa: E402


@pytest.fixture
def table(tmp_path, monkeypatch):
    monkeypatch.setenv("DICECORE_STATE", str(tmp_path))
    settings = Settings()
    settings.state_dir = str(tmp_path)
    settings.capture.source = "sim"
    settings.guard.enabled = False
    reader = Reader(settings)
    return Table(reader, "Alice")


def test_seats_become_the_players(table):
    table.start("Alice")
    table.seat_for("Bob", socket=object())
    assert [s.name for s in table.seats] == ["Alice", "Bob"]
    assert table.reader.game.players == ["Alice", "Bob"]


def test_a_guest_who_reconnects_gets_their_own_seat_back(table):
    table.start("Alice")
    seat, _ = table.seat_for("Bob", socket=object())
    table.leave(seat)
    again, refusal = table.seat_for("Bob", socket=object())
    # Not a new seat at the end of the table: their scorecard column is that seat.
    assert (again, refusal) == (seat, None)


def test_nobody_sits_down_at_a_table_that_is_not_open(table):
    seat, refusal = table.seat_for("Bob", socket=object())
    assert seat is None and "not hosting" in refusal


def test_the_table_fills_up(table):
    table.start("Alice")
    for i in range(20):
        table.seat_for(f"Guest {i}", socket=object())
    assert len(table.seats) == 8
    assert "full" in (table.seat_for("One more", socket=object())[1] or "")


def test_the_pool_travels_with_the_game(table):
    """A guest's simulator throws what the host's game is asking for, not its own guess."""
    table.start("Alice")
    table.reader.game.start("yahtzee", TurnRules(rolls=3, holds=True), ["Alice"])
    assert table.game_json()["pool"] == 5


def test_a_guest_out_of_turn_is_refused_by_the_table_itself(table):
    table.start("Alice")
    seat, _ = table.seat_for("Bob", socket=object())
    table.reader.game.start("yahtzee", TurnRules(rolls=3, holds=True), ["Alice", "Bob"])
    answer = table.apply(seat, protocol.action("book", category="chance"))
    assert answer["type"] == "refused" and answer["reason"] == "It is not your turn."


def test_a_guest_in_turn_plays(table):
    table.start("Alice")
    seat, _ = table.seat_for("Bob", socket=object())
    game = table.reader.game
    game.start("yahtzee", TurnRules(rolls=3, holds=True), ["Alice", "Bob"])
    game._advance()  # straight to Bob's turn; finishing one needs a roll first
    assert game.turn.player == seat
    table.apply(seat, protocol.action(
        "roll", engine="test",
        dice=[{"kind": "d6", "value": v, "confidence": 1.0,
               "box": {"x": 0, "y": 0, "w": 10, "h": 10}} for v in (3, 3, 3, 3, 3)]))
    assert game.turn.values() == [3, 3, 3, 3, 3]
    table.apply(seat, protocol.action("book", category="threes"))
    assert game.cards[seat].scores["threes"] == 15


def test_closing_the_table_empties_it(table):
    table.start("Alice")
    table.seat_for("Bob", socket=object())
    table.stop()
    assert table.seats == [] and table.open is False
