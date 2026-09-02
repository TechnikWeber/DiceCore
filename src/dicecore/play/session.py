"""
The live game: whose turn it is, how many throws are left, and what has been scored.

Kept on the server rather than in the browser, for three reasons. The screen over the tower
has to be able to say "throw 2 of 3" as well. A tab closed by accident must not lose the
game. And a second screen — a phone at the other end of the table — should see the same
thing, not its own copy.

Nothing here decides what a die shows; that happened long before a session sees it.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from ..dice import RollResult
from . import kniffel
from .turns import Turn, TurnRules, apply_roll, end_turn, spend_chip, start_turn, toggle_hold

#: Modes that have a scorecard. Everything else is turns and a running log.
SCORED = {"yahtzee"}


@dataclass
class TurnRecord:
    """One finished turn, for the log the play screen shows down the side."""

    player: int
    number: int
    values: list[int]
    headline: str = ""
    booked: str | None = None
    points: int | None = None
    at: float = field(default_factory=time.time)

    def to_json(self) -> dict[str, Any]:
        return {"player": self.player, "number": self.number, "values": self.values,
                "headline": self.headline, "booked": self.booked, "points": self.points,
                "at": self.at}


class GameSession:
    """
    One game in progress.

    Thread-safe because two things poke it: the reader (from the capture thread, whenever
    dice settle) and the browser (from the request thread). Both are cheap and rare, so one
    lock over the whole object is the right amount of machinery.
    """

    def __init__(self, mode: str = "normal", rules: TurnRules | None = None,
                 players: list[str] | None = None) -> None:
        self._lock = threading.RLock()
        self.mode = mode
        self.rules = rules or TurnRules()
        self.players = players or ["Player 1"]
        self.cards: list[kniffel.Card] = []
        self.log: list[TurnRecord] = []
        self.started = time.time()
        self.turn: Turn = start_turn(self.rules)
        #: What the mode made of the throw this turn is standing on. Kept here rather than
        #: read from the reader's latest result, because once the throws are used up the
        #: tray keeps being looked at and the newest reading is no longer *this turn's* —
        #: showing it would put a headline over a different set of dice.
        self.reading: dict[str, Any] | None = None
        self.message: str = ""
        self._reset_cards()

    # --- lifecycle ----------------------------------------------------------
    def _reset_cards(self) -> None:
        self.cards = ([kniffel.Card(name) for name in self.players]
                      if self.mode in SCORED else [])

    def configure(self, mode: str, rules: TurnRules, players: list[str] | None = None,
                  keep_scores: bool = False) -> None:
        """
        Point the session at a (possibly different) game.

        A change of mode or of the player list starts a new game: carrying a Kniffel card
        into a round of Backgammon, or handing player three's card to a new player three,
        would both be worse than losing the scores.
        """
        with self._lock:
            changed = mode != self.mode or (players is not None and players != self.players)
            self.mode, self.rules = mode, rules
            if players is not None:
                self.players = players or ["Player 1"]
            if changed and not keep_scores:
                self.reset()
            else:
                self.turn.chips_left = min(self.turn.chips_left, rules.chips)

    def reset(self) -> None:
        with self._lock:
            self.log.clear()
            self.started = time.time()
            self.turn = start_turn(self.rules)
            self.reading = None
            self.message = ""
            self._reset_cards()

    # --- the tray -----------------------------------------------------------
    def observe(self, result: RollResult) -> bool:
        """
        A fresh reading arrived. Returns whether it counted as a throw.

        A reading that is stale — nothing moved since the last one — is the same dice being
        looked at again, and counting it would burn a throw for standing still. This is the
        one place the `stale` flag earns its keep.
        """
        with self._lock:
            if result.stale or not result.dice:
                return False
            if self.turn.finished or not self.turn.can_roll:
                self.message = ("No throws left this turn — book it, spend a chip, or end "
                                "the turn." if self.rules.multi else "")
                return False
            apply_roll(self.turn, result.dice, self.rules)
            self.reading = result.reading
            self.message = ""
            return True

    # --- what the player does ----------------------------------------------
    def hold(self, index: int) -> None:
        with self._lock:
            toggle_hold(self.turn, index)

    def chip(self) -> str | None:
        with self._lock:
            _, problem = spend_chip(self.turn)
            self.message = problem or "Chip spent — one more throw."
            return problem

    def book(self, category: str, cross_out: bool = False) -> dict[str, Any]:
        """Score the current dice into a category and hand the tower on."""
        with self._lock:
            if not self.cards:
                raise ValueError("This game has no scorecard.")
            card = self.cards[self.turn.player]
            # Booking a category that scores nothing is a real move — crossing a box out —
            # but it costs you that box for the rest of the game, so it has to be meant.
            # The browser asks; an API caller says so.
            if not cross_out and category in kniffel.CATEGORIES:
                if kniffel.score_for(category, self.turn.values()) == 0:
                    raise ValueError(
                        f"{kniffel.LABELS[category]} scores nothing with these dice. Send "
                        f"cross_out to give the box up deliberately."
                    )
            points = card.book(category, self.turn.values(), cross_out)
            self.log.append(TurnRecord(self.turn.player, self.turn.number,
                                       self.turn.values(), booked=category, points=points))
            self._advance()
            return {"category": category, "points": points, "card": card.to_json()}

    def finish_turn(self, headline: str = "") -> None:
        """End a turn that has nothing to book — every game that is not Kniffel."""
        with self._lock:
            if self.turn.dice:
                self.log.append(TurnRecord(self.turn.player, self.turn.number,
                                           self.turn.values(), headline=headline))
            self._advance()

    def _advance(self) -> None:
        end_turn(self.turn)
        following = (self.turn.player + 1) % max(1, len(self.players))
        number = self.turn.number + 1
        self.turn = start_turn(self.rules, number, following)
        self.reading = None
        self.message = ""
        del self.log[:-40]

    # --- what the screens show ---------------------------------------------
    @property
    def complete(self) -> bool:
        return bool(self.cards) and all(card.complete for card in self.cards)

    def options(self) -> dict[str, int]:
        """What each category would score for the dice on the tray right now."""
        if not self.cards or not self.turn.dice:
            return {}
        return kniffel.options_for(self.turn.values())

    def to_json(self) -> dict[str, Any]:
        with self._lock:
            card = self.cards[self.turn.player] if self.cards else None
            return {
                "mode": self.mode,
                "players": self.players,
                "rules": {"rolls": self.rules.rolls, "holds": self.rules.holds,
                          "chips": self.rules.chips, "multi": self.rules.multi},
                "turn": self.turn.to_json(),
                "reading": self.reading,
                "current_player": self.players[self.turn.player % len(self.players)],
                "cards": [c.to_json() for c in self.cards],
                "options": self.options(),
                "open": card.open_categories() if card else [],
                "log": [record.to_json() for record in reversed(self.log[-12:])],
                "leader": kniffel.leader(self.cards) if self.cards else None,
                "complete": self.complete,
                "message": self.message,
                "started": self.started,
            }
