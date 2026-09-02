"""
Farkle — the second board, and a deliberately different shape from Kniffel.

Kniffel is a fixed number of throws and then a decision. Farkle is the opposite: you throw
as often as you dare, set aside the dice that score, and every throw risks everything the
turn has earned so far. Building both is what shows the turn machine is a machine and not a
Kniffel-shaped hole.

**How it plays with a physical tower.** The dice you set aside leave the tray, so each throw
has fewer dice in it — which the camera sees directly. Set aside all six and the dice are
*hot*: throw all six again and keep going.

House rules vary more here than in any other dice game, so the ones in use are written out:

| | |
|---|---|
| Single 1 / single 5 | 100 / 50 |
| Three of a kind | 100× the face, but three ones are 1000 |
| Four / five / six of a kind | double / four times / eight times the triple |
| Straight 1–6 | 1500 |
| Three pairs | 1500 |
| A throw that scores nothing | **Farkle** — the whole turn is lost |
| Getting on the board | 500 in one turn, by default |
| Winning | 10 000, by default |
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

#: Dice in a full hand.
HAND = 6
#: What a lone one and a lone five are worth.
SINGLES = {1: 100, 5: 50}
#: Multiplier on the triple's value for four, five and six of a kind.
SETS = {3: 1, 4: 2, 5: 4, 6: 8}


@dataclass
class Breakdown:
    """What a set of dice scores, and how many of them were actually used."""

    points: int = 0
    used: int = 0
    parts: list[str] = field(default_factory=list)

    @property
    def scoring(self) -> bool:
        return self.points > 0

    def to_json(self) -> dict[str, Any]:
        return {"points": self.points, "used": self.used, "parts": self.parts}


def breakdown(values: list[int]) -> Breakdown:
    """
    Score a set of dice and count how many of them earned anything.

    `used` is the part that matters for setting dice aside: a selection containing a die
    that scores nothing is not a legal set-aside, and the only way to know is to score it and
    see whether every die was needed.
    """
    if not values:
        return Breakdown()
    counts = Counter(values)

    if len(values) == HAND and set(values) == {1, 2, 3, 4, 5, 6}:
        return Breakdown(1500, HAND, ["straight 1–6: 1500"])
    if len(values) == HAND and sorted(counts.values()) == [2, 2, 2]:
        return Breakdown(1500, HAND, ["three pairs: 1500"])

    points, used, parts = 0, 0, []
    for face in sorted(counts, reverse=True):
        many = counts[face]
        if many >= 3:
            base = 1000 if face == 1 else face * 100
            worth = base * SETS[min(many, HAND)]
            points += worth
            used += many
            parts.append(f"{many}×{face}: {worth}")
            counts[face] = 0
    for face, each in SINGLES.items():
        if counts.get(face):
            points += counts[face] * each
            used += counts[face]
            parts.append(f"{counts[face]}×{face}: {counts[face] * each}")
    return Breakdown(points, used, parts)


def is_legal_selection(values: list[int]) -> bool:
    """
    A set-aside has to earn its keep: every die in it scores, and at least one does.

    Carrying a dead die along would quietly cost you a throw's worth of dice, so it is
    refused rather than scored.
    """
    if not values:
        return False
    result = breakdown(values)
    return result.scoring and result.used == len(values)


@dataclass
class FarkleState:
    """One game of Farkle: what everybody has banked, and what this turn stands to lose."""

    players: int = 1
    target: int = 10000
    #: What you must bank in a single turn before any of it counts.
    entry: int = 500
    banked: list[int] = field(default_factory=list)
    #: Points set aside this turn, lost entirely on a Farkle.
    turn_points: int = 0
    #: Dice still in play this turn. Six again after a hot hand.
    dice_left: int = HAND
    #: Set when the last throw scored nothing at all.
    farkled: bool = False
    #: Whether each player is on the board yet.
    on_board: list[bool] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.banked:
            self.banked = [0] * self.players
        if not self.on_board:
            self.on_board = [False] * self.players

    # --- the two things a player does --------------------------------------
    def set_aside(self, values: list[int]) -> tuple[bool, str]:
        """Bank these dice into the turn and take them off the tray."""
        if self.farkled:
            return False, "This turn is over — the last throw scored nothing."
        if not is_legal_selection(values):
            return False, ("Every die you set aside has to score. Ones and fives on their "
                           "own, or three of a kind and better.")
        if len(values) > self.dice_left:
            return False, f"Only {self.dice_left} dice are in play."
        self.turn_points += breakdown(values).points
        self.dice_left -= len(values)
        if self.dice_left == 0:
            # Hot dice: everything scored, so the whole hand comes back.
            self.dice_left = HAND
        return True, ""

    def bank(self, player: int) -> tuple[int, str]:
        """Take the points and hand the tower on."""
        if self.farkled:
            self.reset_turn()
            return 0, "Farkled — nothing to bank."
        gained = self.turn_points
        if not self.on_board[player] and gained < self.entry:
            self.reset_turn()
            return 0, (f"{gained} is under the {self.entry} needed to get on the board — "
                       f"nothing banked.")
        self.banked[player] += gained
        self.on_board[player] = True
        self.reset_turn()
        return gained, ""

    def farkle(self) -> None:
        """The throw scored nothing. Everything this turn earned is gone."""
        self.farkled = True
        self.turn_points = 0

    def reset_turn(self) -> None:
        self.turn_points = 0
        self.dice_left = HAND
        self.farkled = False

    # --- what the screens show ---------------------------------------------
    @property
    def winner(self) -> int | None:
        best = max(self.banked) if self.banked else 0
        if best < self.target:
            return None
        leaders = [i for i, score in enumerate(self.banked) if score == best]
        return leaders[0] if len(leaders) == 1 else None

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": "farkle", "banked": list(self.banked), "turn_points": self.turn_points,
            "dice_left": self.dice_left, "farkled": self.farkled, "target": self.target,
            "entry": self.entry, "on_board": list(self.on_board), "winner": self.winner,
        }
