"""
Turns: the games where one throw is not the whole story.

Kniffel is the reason this exists. A turn there is up to three throws, and between them the
player keeps some dice and rerolls the rest — so "what did you roll" has no answer until the
turn is over, and a machine that reports every throw as a result is reporting noise.

**Holds are observed, not enforced.** DiceCore cannot stop you picking a die up, and it does
not try to. It notices which dice did not move between two throws and shows that as what you
are keeping; the browser lets you correct it. What is scored at the end is simply what is on
the tray — which is right however the holds were decided, and which is why this file cannot
get a game wrong by mis-guessing a hold.

Everything here is pure. The live game lives in `session.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..dice import Die

#: How far a die may drift and still count as "not moved", as a fraction of its own size.
HOLD_TOLERANCE = 0.4


@dataclass(frozen=True)
class TurnRules:
    """What a turn of this game looks like."""

    #: Throws in a turn before it is over. 1 for most games, 3 for Kniffel.
    rolls: int = 1
    #: Whether keeping dice between throws is part of the game.
    holds: bool = False
    #: Extra throws a player may buy, one throw each. **Per game, not per turn** — a chip
    #: is something you have a few of for the evening and have to decide when to spend, and
    #: refilling them every turn would take that decision away.
    chips: int = 0
    #: Whether the turn ends by itself once the throws are used up, or waits for the player.
    auto_end: bool = True
    #: Throw as often as you dare — Farkle, where the limit is nerve rather than a number.
    #: A turn counter would be meaningless, so the screens show what is at stake instead.
    unlimited: bool = False

    @property
    def multi(self) -> bool:
        return self.rolls > 1 or self.chips > 0 or self.unlimited


@dataclass
class DieSlot:
    """One die on the tray, and whether the player is keeping it."""

    kind: str
    value: int
    held: bool = False
    #: What colour the die is, when the engine was asked to look. None otherwise.
    colour: str | None = None
    #: Where it was, so the next throw can tell "kept" from "rerolled".
    x: int = 0
    y: int = 0
    size: int = 1

    def to_json(self) -> dict[str, Any]:
        return {"kind": self.kind, "value": self.value, "held": self.held,
                "colour": self.colour}


@dataclass
class Turn:
    """One player's turn, from the first throw to the moment it is booked."""

    number: int = 1
    player: int = 0
    rolls_used: int = 0
    #: Base throws plus every chip spent this turn.
    rolls_allowed: int = 1
    chips_left: int = 0
    dice: list[DieSlot] = field(default_factory=list)
    finished: bool = False
    #: Set when the turn ended because the throws ran out rather than by a decision.
    spent: bool = False
    #: No throw limit — the turn ends when the player banks or the game takes it away.
    unlimited: bool = False

    @property
    def rolls_left(self) -> int:
        return max(0, self.rolls_allowed - self.rolls_used)

    @property
    def can_roll(self) -> bool:
        return not self.finished and (self.unlimited or self.rolls_left > 0)

    @property
    def can_spend_chip(self) -> bool:
        """A chip is only worth spending once the ordinary throws are gone."""
        return not self.finished and self.chips_left > 0 and self.rolls_left == 0

    def values(self) -> list[int]:
        return [slot.value for slot in self.dice]

    def to_json(self) -> dict[str, Any]:
        return {
            "number": self.number, "player": self.player, "unlimited": self.unlimited,
            "rolls_used": self.rolls_used, "rolls_allowed": self.rolls_allowed,
            "rolls_left": self.rolls_left, "chips_left": self.chips_left,
            "dice": [slot.to_json() for slot in self.dice],
            "finished": self.finished, "spent": self.spent,
            "can_roll": self.can_roll, "can_spend_chip": self.can_spend_chip,
        }


def start_turn(rules: TurnRules, number: int = 1, player: int = 0,
               chips_left: int | None = None) -> Turn:
    return Turn(number=number, player=player, rolls_allowed=rules.rolls,
                chips_left=rules.chips if chips_left is None else chips_left,
                unlimited=rules.unlimited)


def detect_holds(previous: list[DieSlot], dice: list[Die]) -> list[bool]:
    """
    Which of the new dice are the ones that never left the tray.

    Matched on position: a die that was not picked up is within a fraction of its own size of
    where it was. That is the only signal available — DiceCore cannot see a hand deciding —
    and it is why the browser can override the answer.
    """
    held: list[bool] = []
    for die in dice:
        centre_x, centre_y = die.box.center
        match = None
        for slot in previous:
            if not slot.held:
                continue
            span = max(1, slot.size)
            if (abs(slot.x - centre_x) <= span * HOLD_TOLERANCE
                    and abs(slot.y - centre_y) <= span * HOLD_TOLERANCE
                    and slot.value == die.value):
                match = slot
                break
        held.append(match is not None)
    return held


def slots_from(dice: list[Die], held: list[bool] | None = None) -> list[DieSlot]:
    flags = held or [False] * len(dice)
    slots = []
    for die, flag in zip(dice, flags, strict=False):
        x, y = die.box.center
        slots.append(DieSlot(die.kind, die.value, flag, die.colour, x, y,
                             max(die.box.w, die.box.h)))
    return slots


def apply_roll(turn: Turn, dice: list[Die], rules: TurnRules) -> Turn:
    """
    Fold a fresh reading of the tray into the turn.

    The dice on the tray *are* the turn's dice — a held die is still lying there, so nothing
    has to be merged and nothing can be lost by a hold guessed wrongly. All the holds do is
    tell the player and the screen what is being kept.
    """
    if turn.finished:
        return turn
    held = detect_holds(turn.dice, dice) if (rules.holds and turn.dice) else None
    turn.dice = slots_from(dice, held)
    turn.rolls_used += 1
    if rules.auto_end and not rules.unlimited and turn.rolls_left == 0 and turn.chips_left == 0:
        turn.finished = True
        turn.spent = True
    return turn


def toggle_hold(turn: Turn, index: int) -> Turn:
    """The player disagrees with what was detected — or is deciding in advance."""
    if 0 <= index < len(turn.dice) and not turn.finished:
        turn.dice[index].held = not turn.dice[index].held
    return turn


def spend_chip(turn: Turn) -> tuple[Turn, str | None]:
    """
    Buy one more throw.

    Refused rather than silently ignored when there are still ordinary throws left: spending
    a chip you did not need is the kind of mistake a game should not let you make by
    fumbling a button.
    """
    if turn.finished:
        return turn, "This turn is over."
    # Checked before the purse: in a game with no throw limit a chip buys nothing whether
    # you have three or none, and "no chips left" would send someone looking for more.
    if turn.unlimited:
        return turn, "This game has no throw limit — a chip would buy nothing."
    if turn.chips_left <= 0:
        return turn, "No chips left."
    if turn.rolls_left > 0:
        return turn, f"{turn.rolls_left} ordinary throw(s) left — no need for a chip yet."
    turn.chips_left -= 1
    turn.rolls_allowed += 1
    turn.finished = False
    turn.spent = False
    return turn, None


def end_turn(turn: Turn) -> Turn:
    turn.finished = True
    return turn
