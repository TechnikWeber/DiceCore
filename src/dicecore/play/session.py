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
from . import farkle as farkle_rules
from . import kniffel
from .turns import Turn, TurnRules, apply_roll, end_turn, spend_chip, start_turn, toggle_hold

#: Which board a mode plays on. Everything not listed is turns and a running log.
BOARDS = {
    "yahtzee": kniffel.STANDARD,
    "yahtzee_extreme": kniffel.EXTREME,
    "farkle": "farkle",
}


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
                 players: list[str] | None = None,
                 params: dict[str, Any] | None = None) -> None:
        self._lock = threading.RLock()
        self.mode = mode
        self.rules = rules or TurnRules()
        #: The mode's own numbers — Farkle's target and entry threshold live here.
        self.params: dict[str, Any] = dict(params or {})
        self.players = players or ["Player 1"]
        self.cards: list[kniffel.Card] = []
        #: Farkle's board, when that is the game. Push-your-luck rather than a card, which
        #: is the whole reason for building a second one.
        self.farkle: farkle_rules.FarkleState | None = None
        #: Chips left, per player, for the whole game. Spending one is a decision about the
        #: evening rather than about this turn, which is the point of having them.
        self.chips: list[int] = []
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
    @property
    def sheet(self) -> kniffel.Sheet | None:
        board = BOARDS.get(self.mode)
        return board if isinstance(board, kniffel.Sheet) else None

    def _reset_cards(self) -> None:
        sheet = self.sheet
        self.cards = ([kniffel.Card(name, sheet) for name in self.players] if sheet else [])
        self.farkle = (farkle_rules.FarkleState(
            players=len(self.players),
            target=int(self.params.get("target", 10000)),
            entry=int(self.params.get("entry", 500)),
        ) if BOARDS.get(self.mode) == "farkle" else None)
        self.chips = [self.rules.chips for _ in self.players]

    def configure(self, mode: str, rules: TurnRules, players: list[str] | None = None,
                  keep_scores: bool = False, params: dict[str, Any] | None = None) -> None:
        """
        Point the session at a (possibly different) game.

        A change of mode or of the player list starts a new game: carrying a Kniffel card
        into a round of Backgammon, or handing player three's card to a new player three,
        would both be worse than losing the scores.
        """
        with self._lock:
            changed = mode != self.mode or (players is not None and players != self.players)
            self.mode, self.rules = mode, rules
            if params is not None:
                changed = changed or params != self.params
                self.params = dict(params)
            if players is not None:
                self.players = players or ["Player 1"]
            if changed and not keep_scores:
                self.reset()
            else:
                # Never hand someone more chips than the new rules allow, and never take
                # away ones they have already earned the right to by not spending them.
                self.chips = [min(left, rules.chips) for left in self.chips]
                self.chips += [rules.chips] * (len(self.players) - len(self.chips))
                self.turn.chips_left = self.chips[self.turn.player % len(self.chips)]

    def reset(self) -> None:
        with self._lock:
            self.log.clear()
            self.started = time.time()
            self._reset_cards()
            self.turn = start_turn(self.rules, chips_left=self.chips[0] if self.chips else 0)
            self.reading = None
            self.message = ""

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
            if self.farkle is not None and not farkle_rules.breakdown(
                    self.turn.values()).scoring:
                # A throw with nothing in it takes the whole turn with it. That is the game,
                # and the screen has to say so loudly rather than wait to be asked.
                self.farkle.farkle()
                self.message = "Farkle! Nothing in that throw — the turn is lost."
            return True

    # --- what the player does ----------------------------------------------
    def hold(self, index: int) -> None:
        with self._lock:
            toggle_hold(self.turn, index)

    def chip(self) -> str | None:
        with self._lock:
            _, problem = spend_chip(self.turn)
            if problem is None:
                # The turn's counter and the player's purse have to stay in step: the turn
                # is what enforces "not while throws remain", the purse is what runs out.
                index = self.turn.player % max(1, len(self.chips))
                if self.chips:
                    self.chips[index] = max(0, self.chips[index] - 1)
            self.message = problem or "Chip spent — one more throw."
            return problem

    # --- Farkle ------------------------------------------------------------
    def set_aside(self) -> dict[str, Any]:
        """Take the held dice off the tray and put their points into the turn."""
        with self._lock:
            if self.farkle is None:
                raise ValueError("This game does not set dice aside.")
            chosen = [slot.value for slot in self.turn.dice if slot.held]
            ok, problem = self.farkle.set_aside(chosen)
            self.message = problem or (
                f"{farkle_rules.breakdown(chosen).points} set aside — "
                f"{self.farkle.turn_points} this turn, {self.farkle.dice_left} dice to throw.")
            if ok:
                # The dice that were set aside have physically left the tray, so the turn
                # starts the next throw with nothing held.
                self.turn.dice = []
            return {"ok": ok, "detail": problem, "farkle": self.farkle.to_json()}

    def bank(self) -> dict[str, Any]:
        """Take the turn's points and hand the tower on."""
        with self._lock:
            if self.farkle is None:
                raise ValueError("This game has nothing to bank.")
            player = self.turn.player
            gained, problem = self.farkle.bank(player)
            self.log.append(TurnRecord(player, self.turn.number, self.turn.values(),
                                       headline=f"{gained}" if gained else "Farkle",
                                       points=gained))
            self._advance()
            self.message = problem or f"{gained} banked."
            return {"ok": not problem, "detail": problem, "gained": gained,
                    "farkle": self.farkle.to_json()}

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
        left = self.chips[following] if following < len(self.chips) else self.rules.chips
        self.turn = start_turn(self.rules, number, following, chips_left=left)
        self.reading = None
        self.message = ""
        del self.log[:-40]

    # --- what the screens show ---------------------------------------------
    @property
    def complete(self) -> bool:
        if self.farkle is not None:
            return self.farkle.winner is not None
        return bool(self.cards) and all(card.complete for card in self.cards)

    def options(self) -> dict[str, int]:
        """What each category would score for the dice on the tray right now."""
        sheet = self.sheet
        if not sheet or not self.turn.dice:
            return {}
        return kniffel.options_for(self.turn.values(), sheet)

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
                "sheet": kniffel.sheet_json(self.sheet) if self.sheet else None,
                "farkle": self.farkle.to_json() if self.farkle else None,
                "selection": (farkle_rules.breakdown(
                    [s.value for s in self.turn.dice if s.held]).to_json()
                    if self.farkle else None),
                "chips": list(self.chips),
                "options": self.options(),
                "open": card.open_categories() if card else [],
                "log": [record.to_json() for record in reversed(self.log[-12:])],
                "leader": (self.farkle.winner if self.farkle
                           else (kniffel.leader(self.cards) if self.cards else None)),
                "complete": self.complete,
                "message": self.message,
                "started": self.started,
            }
