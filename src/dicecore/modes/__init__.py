"""
Game modes: the same dice, read the way the game at this table reads them.

DiceCore's job stops at "these faces are showing". What that *means* — a sum, three
successes, a full house, a 43 against a target of 55 — is the game's business, and it is the
difference between a machine that is useful for one system and one that is useful at any
table. A mode is a table entry (`catalogue.py`) plus a pure function (`scoring.py`).

Nothing here touches a camera, and nothing here decides what a die shows. A mode only reads.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..dice import Die
from . import scoring
from .catalogue import ALL_KINDS, DEFAULT, MODES, GameMode, mode_by_id
from .fairness import Tally
from .scoring import Score

__all__ = [
    "MODES", "DEFAULT", "ALL_KINDS", "GameMode", "Score", "Tally", "ModeSession",
    "interpret", "mode_by_id", "expected_count",
]

_RANGE = re.compile(r"^(\d+)\s*[–-]\s*(\d+)$")


def expected_count(spec: str) -> tuple[int, int] | None:
    """`"2"` → (2, 2), `"1–6"` → (1, 6), `"any"` → None."""
    spec = spec.strip()
    if spec in ("any", ""):
        return None
    if spec.isdigit():
        return int(spec), int(spec)
    match = _RANGE.match(spec)
    return (int(match.group(1)), int(match.group(2))) if match else None


@dataclass
class ModeSession:
    """
    What a mode remembers between throws.

    Only two modes need any: an exploding roll that is still open, and the running tally a
    fairness test is built from. Kept in one object so switching modes can clear the lot,
    and so nothing else in DiceCore has to know that some modes have memory.
    """

    #: The running total of an exploding roll that has not landed short yet.
    carried: int = 0
    #: Face counts for the fairness test.
    tally: Tally = field(default_factory=Tally)
    #: Which mode this state belongs to, so a switch does not carry it over.
    mode: str = DEFAULT

    def reset(self) -> None:
        self.carried = 0
        self.tally.reset()

    def for_mode(self, mode_id: str) -> None:
        if mode_id != self.mode:
            self.reset()
            self.mode = mode_id

    def to_json(self) -> dict[str, Any]:
        return {"mode": self.mode, "carried": self.carried,
                "tally": self.tally.verdict() if self.tally.rolls else None}


def parameters(mode: GameMode, overrides: dict[str, Any] | None) -> dict[str, Any]:
    """A mode's defaults with the user's changes on top, ignoring keys it does not have."""
    values = dict(mode.defaults)
    for key, value in (overrides or {}).items():
        if key in values:
            values[key] = value
    return values


def check_dice(mode: GameMode, dice: list[Die]) -> list[str]:
    """
    Complain about the tray before scoring it.

    A mode that expects two dice and finds three is the most common real mistake at a table —
    a die left over from the last throw. Saying so is more useful than silently adding it in.
    """
    warnings: list[str] = []
    bounds = expected_count(mode.dice)
    if bounds is not None:
        low, high = bounds
        if not (low <= len(dice) <= high):
            wanted = f"{low}" if low == high else f"{low}–{high}"
            verb = "is" if len(dice) == 1 else "are"
            warnings.append(
                f"{mode.label} is played with {wanted} dice; there {verb} {len(dice)} "
                f"on the tray."
            )
    strangers = sorted({d.kind for d in dice} - set(mode.kinds))
    if strangers:
        warnings.append(
            f"{', '.join(strangers)} {'is' if len(strangers) == 1 else 'are'} not part of "
            f"{mode.label} — set the mode's dice under Detection, or pick another mode."
        )
    return warnings


def interpret(dice: list[Die], mode_id: str = DEFAULT, overrides: dict[str, Any] | None = None,
              session: ModeSession | None = None, d10_style: str = "0-9",
              zero_is_ten: bool = True) -> Score:
    """
    Read a set of faces the way this mode reads them.

    Unread dice are dropped and reported rather than scored. A rule that
    silently treated "I could not read this one" as a zero would turn a missing die into a
    wrong answer, which is the one failure this project refuses to produce.
    """
    mode = mode_by_id(mode_id) or mode_by_id(DEFAULT)
    assert mode is not None
    values = parameters(mode, overrides)
    session = session or ModeSession()
    session.for_mode(mode.id)

    scorable = scoring.readable(dice)
    warnings = check_dice(mode, dice)
    unread = len(dice) - len(scorable)
    if unread:
        warnings.append(
            f"{unread} {'die' if unread == 1 else 'dice'} could not be read and "
            f"{'is' if unread == 1 else 'are'} left out of the score."
        )

    rule = values.get("rule", mode.rule) if mode.id == "custom" else mode.rule
    score = _apply(rule, scorable, values, session, d10_style, zero_is_ten)
    score.warnings = warnings + score.warnings
    score.extras["mode"] = mode.id
    score.extras["rule"] = rule
    return score


def _apply(rule: str, dice: list[Die], values: dict[str, Any], session: ModeSession,
           d10_style: str, default_zero_is_ten: bool = True) -> Score:
    # A zero is worth ten in nearly every game that uses a 0–9 die, so that is the answer
    # unless the table says otherwise — and a mode may still override the table.
    zero_is_ten = bool(values.get("zero_is_ten", default_zero_is_ten))

    if rule == "sum":
        return scoring.score_sum(dice, zero_is_ten)
    if rule == "rpg":
        return scoring.score_rpg(dice, d10_style)
    if rule == "pool":
        return scoring.score_pool(dice, int(values.get("threshold", 4)),
                                  bool(values.get("double_on_max", False)),
                                  d10_style, zero_is_ten)
    if rule == "best":
        return scoring.score_best(dice, str(values.get("take", "high")), zero_is_ten)
    if rule == "under":
        return scoring.score_under(dice, int(values.get("target", 50)), zero_is_ten,
                                   bool(values.get("percentile", True)))
    if rule == "yahtzee":
        return scoring.score_yahtzee(dice)
    if rule == "farkle":
        return scoring.score_farkle(dice)
    if rule == "backgammon":
        return scoring.score_backgammon(dice)
    if rule == "maexchen":
        return scoring.score_maexchen(dice)
    if rule == "single":
        return scoring.score_single(dice)
    if rule == "exploding":
        score = scoring.score_exploding(dice, session.carried, d10_style)
        # The carry is the whole mechanic: keep the running total while a die is still
        # showing its maximum, and drop it the moment one lands short.
        session.carried = score.extras["total"] if score.extras["open"] else 0
        return score
    if rule == "fairness":
        for die in dice:
            session.tally.kind = die.kind
            session.tally.observe(die.value)
        verdict = session.tally.verdict()
        return Score(
            headline=f"{verdict['rolls']} throws",
            detail=verdict["wording"],
            value=verdict["rolls"],
            extras=verdict,
        )
    return scoring.score_sum(dice, zero_is_ten)
