"""
The vocabulary every part of DiceCore speaks.

Pure data, no dependencies — the API serialises these, the engines produce them, the
dataset stores them and the tests assert on them. Nothing here may import numpy, OpenCV
or anything else that will not install on an ARMv6 Pi Zero.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any

# --- Dice kinds -------------------------------------------------------------------

#: Faces per kind. `d10` is the 0–9 die, `d100` the tens die (00, 10, … 90).
#:
#: The seven of a roleplaying set, plus the two small ones that turn up with them: a d3
#: (a real die, though most tables read one off a d6) and a d2. Kinds beyond these exist —
#: d5, d7, d14, d16, d24, d30 from the Dice Lab and Zocchi sets — and each is one line
#: here plus one in `READING`, so add yours if you own them.
DIE_FACES: dict[str, int] = {
    "d2": 2,
    "d3": 3,
    "d4": 4,
    "d6": 6,
    "d8": 8,
    "d10": 10,
    "d100": 10,
    "d12": 12,
    "d20": 20,
}

#: How a kind is read. Pipped dice are counted, numeral dice are recognised. A d6 can be
#: either — pips are the common case, but numeral d6 exist and are read like a d8.
READING = {
    "d2": "numeral",
    "d3": "numeral",
    "d4": "numeral",
    "d6": "pips",
    "d8": "numeral",
    "d10": "numeral",
    "d100": "numeral",
    "d12": "numeral",
    "d20": "numeral",
}

DIE_KINDS = tuple(DIE_FACES)


#: How the ten-sided dice in this set are printed. Modern ones show 0–9 and let the game
#: decide what the 0 is worth; older ones are printed 1–10, where the 10 is a two-digit
#: glyph on one face. It changes the class list a model is trained on, so it is a property
#: of the dice, not of the game.
D10_STYLES = ("0-9", "1-10")


def values_for(kind: str, d10_style: str = "0-9") -> list[int]:
    """The values a kind can show. Needed by the label UI and by the classifier head."""
    if kind == "d100":
        return [0, 10, 20, 30, 40, 50, 60, 70, 80, 90]
    if kind == "d10":
        return list(range(1, 11)) if d10_style == "1-10" else list(range(0, 10))
    return list(range(1, DIE_FACES[kind] + 1))


def is_valid(kind: str, value: int, d10_style: str = "0-9") -> bool:
    return kind in DIE_FACES and value in values_for(kind, d10_style)


def best_total(kinds: list[str], d10_style: str = "0-9") -> int:
    """
    The most these dice could possibly show.

    What makes a total worth celebrating depends on how many dice are on the tray and what
    they are: 18 is impossible with two six-siders and unremarkable with six. A fixed
    threshold is therefore always wrong for some table, and this is what a relative one is
    measured against.
    """
    return sum(max(values_for(kind, d10_style), default=0) for kind in kinds)


# --- Results ----------------------------------------------------------------------


@dataclass
class Box:
    """Axis-aligned pixel box in the captured frame. Ints, so it survives JSON intact."""

    x: int
    y: int
    w: int
    h: int

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.w // 2, self.y + self.h // 2

    @property
    def area(self) -> int:
        return self.w * self.h


@dataclass
class Die:
    """One die as read from one frame."""

    kind: str
    value: int
    box: Box
    #: 0..1. The classic engine derives it from how cleanly the pips separated; the model
    #: engine reports the softmax. Consumers use it to decide whether to ask for a reroll.
    confidence: float = 1.0
    #: Set when the engine is unsure but has a runner-up worth showing in the label UI.
    alternatives: list[int] = field(default_factory=list)
    #: What colour the die is, when colour detection is on: "red", "white", … or None.
    #: Rides along on the result; nothing in DiceCore decides anything from it, because
    #: which games care is the consumer's business.
    colour: str | None = None

    @property
    def label(self) -> str:
        """`d20:14` — the short form used in logs and in the notation string."""
        return f"{self.kind}:{self.value}"

    @property
    def unread(self) -> bool:
        """
        The engine found this die but could not read it.

        Not the same as `value == 0`, which a d10 legitimately shows: a die printed 0–9 has
        a zero face, and treating it as "unknown" quietly dropped it out of every sum. An
        unread die is one with no confidence in its value at all.
        """
        return self.value == 0 and self.confidence == 0.0


@dataclass
class RollResult:
    """What one settled roll amounts to. This is the payload of the whole project."""

    dice: list[Die] = field(default_factory=list)
    #: Which engine produced it (`classic`, `model`, `remote:<host>`) — kept because a
    #: number without its provenance is unfixable when it turns out to be wrong.
    engine: str = "unknown"
    at: float = field(default_factory=time.time)
    #: Milliseconds spent in the engine, capture excluded.
    took_ms: float = 0.0
    #: Non-fatal complaints: "two dice overlap", "frame is dark", "no tray configured".
    warnings: list[str] = field(default_factory=list)
    #: Where the frame was stored, if it was.
    frame_id: str | None = None
    #: What the active game mode made of these faces — headline, detail, extras. None when
    #: no mode ran. Additive: a consumer that ignores it still gets `total` and `dice`.
    reading: dict[str, Any] | None = None
    #: Fair play, see integrity.py: unverified | pending | clean | disturbed | void. A
    #: consumer that ignores this field still gets a number; one that cares can refuse a
    #: `void` without knowing anything about how the watching works.
    verdict: str = "unverified"
    #: The full record of what the guard saw, or None when it did not run.
    integrity: dict[str, Any] | None = None
    #: True when nothing moved since the last reading and the dice read the same — this is
    #: the previous roll being looked at again, not a new throw. Display modes ignore it;
    #: anything that counts rolls must not count a stale one twice.
    stale: bool = False

    @property
    def usable(self) -> bool:
        """False only for `void` — the one verdict that means "do not count this"."""
        return self.verdict != "void"

    @property
    def total(self) -> int:
        return sum(d.value for d in self.dice)

    @property
    def count(self) -> int:
        return len(self.dice)

    @property
    def notation(self) -> str:
        """`2d20+1d6 → 14, 3, 5` — the human/text form for chat bots and logs."""
        if not self.dice:
            return "no dice"
        order = [k for k in sorted(DIE_KINDS, key=lambda k: DIE_FACES[k])
                 if any(d.kind == k for d in self.dice)]
        groups = "+".join(f"{sum(1 for d in self.dice if d.kind == k)}{k}" for k in order)
        # Values follow the same grouping as the summary, or "2d6+1d20 → 3, 4, 14" would
        # list them in an order that does not match the groups it just announced. A die the
        # engine located but could not read is a "?", never a 0 — printing 0 for "I don't
        # know" is the kind of number a consumer would happily add up.
        rolled = ", ".join("?" if d.unread else str(d.value)
                           for k in order for d in self.dice if d.kind == k)
        return f"{groups} → {rolled}"

    def to_json(self) -> dict[str, Any]:
        out = asdict(self)
        # `unread` is a property, so asdict does not carry it — and the UI and every
        # consumer need it to tell "could not read" from "a d10 showing zero".
        for die, raw in zip(self.dice, out["dice"], strict=True):
            raw["unread"] = die.unread
        out["total"] = self.total
        out["count"] = self.count
        out["notation"] = self.notation
        out["usable"] = self.usable
        return out


@dataclass
class Frame:
    """
    A captured image plus what we know about the capture.

    `image` is a numpy array when a vision stack is installed, and `None` in the agent
    shape where the Pi only forwards `jpeg` without ever decoding it. Code that needs
    pixels must say so and fail with a clear message, not silently assume numpy is there.
    """

    image: Any = None
    jpeg: bytes | None = None
    at: float = field(default_factory=time.time)
    source: str = "unknown"
    #: Width, height in pixels — filled in even when only `jpeg` is present.
    size: tuple[int, int] | None = None
