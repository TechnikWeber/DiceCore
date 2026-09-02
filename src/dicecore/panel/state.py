"""
What the little screen and the lamps are being asked to show.

One state for both, deliberately. A display that says the number and an LED that says
"you may throw again" have to agree, and the only way to guarantee that is to derive both
from the same value rather than to let each device interpret the reader's events.

Pure: no pixels, no pins. `render.py` turns this into an image, `signals.py` into GPIO
levels, and this module can be reasoned about on its own.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .. import dice as dicevocab
from ..dice import RollResult

# --- phases -----------------------------------------------------------------------

#: Nothing has happened yet. Throw whenever you like.
IDLE = "idle"
#: The dice are in the air or still rolling.
ROLLING = "rolling"
#: They have stopped and the picture is being read. Sub-second.
READING = "reading"
#: The number is in — but the tray is still being watched, so hands off.
RESULT = "result"
#: The watch is over. This is the moment you may throw again.
READY = "ready"
#: The dice are not what was read. The number does not count.
VOID = "void"
#: Something is broken and nobody should wait for a number.
ERROR = "error"

PHASES = (IDLE, ROLLING, READING, RESULT, READY, VOID, ERROR)

#: Phases in which throwing again is the right thing to do.
GO = (IDLE, READY)
#: Phases in which the tray must be left alone.
WAIT = (ROLLING, READING, RESULT)


@dataclass
class Presentation:
    """One frame of "what is going on", as shown by every output at once."""

    phase: str = IDLE
    #: What belongs on the panel in big letters. A mode decides this — "18", "3 successes",
    #: "Full house". Falls back to the plain total when no mode has spoken.
    headline: str | None = None
    total: int | None = None
    notation: str = ""
    dice: list[tuple[str, int]] = field(default_factory=list)
    verdict: str = "unverified"
    #: A roll worth a small celebration — see `is_celebration`.
    celebrate: bool = False
    #: The other end of the scale: a natural 1.
    lament: bool = False
    #: A line for the screen when there is no number: an error, or a hint.
    message: str = ""
    #: Where this throw sits in a turn, for the games that have turns: used, allowed, left,
    #: chips, player. None for a game where one throw is the whole story.
    turn: dict[str, Any] | None = None
    #: Frame counter while an animation plays; 0 is the still picture.
    anim: int = 0
    at: float = field(default_factory=time.time)

    @property
    def go(self) -> bool:
        """Whether it is your turn to throw. This is what the green lamp means."""
        return self.phase in GO

    @property
    def busy(self) -> bool:
        return self.phase in WAIT

    @property
    def big(self) -> str | None:
        """The one string the screen shows large."""
        if self.headline:
            return self.headline
        return None if self.total is None else str(self.total)

    def to_json(self) -> dict[str, Any]:
        return {
            "phase": self.phase, "headline": self.headline, "big": self.big,
            "total": self.total, "notation": self.notation,
            "dice": [{"kind": k, "value": v} for k, v in self.dice],
            "turn": self.turn,
            "verdict": self.verdict, "celebrate": self.celebrate, "lament": self.lament,
            "message": self.message, "go": self.go, "at": self.at,
        }


# --- what counts as a good roll ---------------------------------------------------


def is_celebration(result: RollResult, mode: str, total_at_least: int) -> bool:
    """
    Whether this roll deserves the animation.

    `max_die` is the default because it is the moment everyone at the table reacts to
    anyway — a natural 20, a six. A total threshold is for games where the sum is the
    thing. Unread dice never celebrate: the machine has no idea what it is
    looking at, and a party over a number it could not read is worse than silence.
    """
    if mode == "off" or not result.dice:
        return False
    if any(die.unread for die in result.dice):
        return False
    if mode == "total":
        return result.total >= total_at_least
    if mode == "max_die":
        return any(die.value == max(dicevocab.values_for(die.kind)) for die in result.dice)
    return False


def is_lament(result: RollResult, enabled: bool) -> bool:
    """
    A natural 1 — the other thing the whole table reacts to.

    Only for dice whose faces start at 1. A d10 counts from 0 and a d100 in tens, so their
    lowest face is a 0 that means ten or means nothing depending on the game; nobody groans
    at it, and inventing a rule for it would only produce a beep at the wrong moment.
    """
    if not enabled or not result.dice:
        return False
    if any(die.unread for die in result.dice):
        return False
    return any(die.value == 1 and min(dicevocab.values_for(die.kind)) == 1
               for die in result.dice)


def presentation_for(result: RollResult, phase: str, celebrate_mode: str = "max_die",
                     celebrate_total: int = 18, lament_on_min: bool = True) -> Presentation:
    """
    Build the frame for a finished (or in-flight) roll.

    When a game mode has read the roll, *it* decides what goes on the screen and what is
    worth celebrating — a Kniffel and four successes are not things a generic rule about
    maximum faces could ever recognise. Without a mode, the old rule still applies.
    """
    reading = result.reading or {}
    return Presentation(
        phase=phase,
        headline=reading.get("headline"),
        total=result.total if result.dice else None,
        notation=reading.get("detail") or result.notation,
        dice=[(d.kind, d.value) for d in result.dice],
        verdict=result.verdict,
        celebrate=bool(reading["celebrate"]) if "celebrate" in reading
        else is_celebration(result, celebrate_mode, celebrate_total),
        lament=bool(reading["lament"]) if "lament" in reading
        else is_lament(result, lament_on_min),
    )


def waiting(phase: str = READING, message: str = "") -> Presentation:
    return Presentation(phase=phase, message=message)


def failed(message: str) -> Presentation:
    return Presentation(phase=ERROR, message=message)
