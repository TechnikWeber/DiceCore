"""
Fair play: deciding whether a reading can still be trusted.

What this can and cannot do, stated up front because it decides how the results should be
read. DiceCore watches the tray with the same camera it reads the dice with. That makes it
good at catching the cheating that actually happens at a table — a hand going back in to
turn a die over, a die nudged while nobody is looking, the same lucky roll reported twice.
It is **tamper evidence, not tamper proof**: anyone who can cover the lens, move the
camera, or edit the config can defeat it, and nothing camera-shaped will ever change that.
So DiceCore never claims a roll was fair. It says either "nothing happened between the
throw and this number" or "here is exactly what happened", and lets the game decide.

Everything in this module is pure: comparisons, classification and policy. The pixels live
in `guard.py`, so the rules that decide whether someone cheated can be tested on numbers.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from .dice import Die

# --- verdicts ---------------------------------------------------------------------

#: The guard did not run — it is off, or the caller asked for an unverified read.
UNVERIFIED = "unverified"
#: Read and reported, but the watch window is still open.
PENDING = "pending"
#: Watched to the end of the hold window; nothing touched the tray.
CLEAN = "clean"
#: Something reached in, but the dice read the same afterwards. Usable, and flagged.
DISTURBED = "disturbed"
#: The dice are not what was read. The number must not be used.
VOID = "void"

VERDICTS = (UNVERIFIED, PENDING, CLEAN, DISTURBED, VOID)

#: How bad an event is. `info` is a note, `warn` is worth showing, `fault` voids under a
#: policy that voids at all.
INFO, WARN, FAULT = "info", "warn", "fault"


@dataclass
class Event:
    """One thing the guard saw. The list of these is the whole explanation of a verdict."""

    kind: str
    severity: str
    detail: str
    at: float = field(default_factory=time.time)

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Integrity:
    """What the guard did, attached to the result it was watching."""

    verdict: str = UNVERIFIED
    events: list[Event] = field(default_factory=list)
    #: Seconds the tray was watched after the reading.
    held_s: float = 0.0
    #: sha256 over the frame and the reading — an identifier for this exact roll, and the
    #: thing that makes a replayed frame recognisable.
    seal: str | None = None
    #: False while the hold window is still running.
    settled_check: bool = False

    def to_json(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "events": [e.to_json() for e in self.events],
            "held_s": round(self.held_s, 2),
            "seal": self.seal,
            "settled_check": self.settled_check,
        }

    @property
    def faults(self) -> list[Event]:
        return [e for e in self.events if e.severity == FAULT]


# --- comparing two readings of the same tray ---------------------------------------


def _multiset(dice: list[Die]) -> list[str]:
    return sorted(f"{d.kind}:{d.value}" for d in dice)


def compare_readings(before: list[Die], after: list[Die], move_tolerance: float = 0.4
                     ) -> list[str]:
    """
    What changed between the reading we published and the tray as it is now.

    Deliberately compares three separate things, because they are three different kinds of
    cheating: how many dice there are (one added or palmed), what they show (one turned
    over), and where they are (one nudged, which may or may not have changed its face).
    Position is compared last and with a tolerance, since a die that has not moved still
    wobbles by a pixel or two between frames.
    """
    differences: list[str] = []
    if len(before) != len(after):
        was, now_ = len(before), len(after)
        differences.append(f"{was} {'die' if was == 1 else 'dice'} were read, "
                           f"{now_} {'is' if now_ == 1 else 'are'} on the tray now")
    before_values, after_values = _multiset(before), _multiset(after)
    if before_values != after_values:
        differences.append(f"the dice read {', '.join(before_values) or 'nothing'} and now read "
                           f"{', '.join(after_values) or 'nothing'}")
    if len(before) == len(after) and before_values == after_values:
        for index, (old, new) in enumerate(zip(before, after, strict=True)):
            span = max(1, max(old.box.w, old.box.h))
            shift = max(abs(old.box.center[0] - new.box.center[0]),
                        abs(old.box.center[1] - new.box.center[1]))
            if shift > span * move_tolerance:
                differences.append(
                    f"die {index + 1} ({old.label}) moved {shift}px without changing face")
    return differences


# --- policy ------------------------------------------------------------------------

#: Watch nothing.
OFF = "off"
#: Watch and report, but never withhold a number — the game decides what to do with it.
FLAG = "flag"
#: A tray that was interfered with produces no number at all.
VOID_POLICY = "void"

POLICIES = (
    (OFF, "Off — do not watch the tray after a reading"),
    (FLAG, "Flag — always report the number, say what happened to it"),
    (VOID_POLICY, "Void — a disturbed roll is discarded"),
)


def decide(events: list[Event], policy: str, void_on_touch: bool = False) -> str:
    """
    Turn what was seen into a verdict.

    The rule that matters: a hand in the tray is *suspicious*, a changed reading is
    *disqualifying*. Someone reaching past the tower to grab their drink is the common case
    and must not silently throw away a legitimate roll — so under the default policy the
    reach is recorded and only a reading that actually changed voids the number.
    `void_on_touch` is for the stricter table where nothing may enter the tray at all.
    """
    if policy == OFF:
        return UNVERIFIED
    faults = [e for e in events if e.severity == FAULT]
    touched = [e for e in events if e.kind in ("reach", "motion")]
    if faults:
        return VOID if policy == VOID_POLICY else DISTURBED
    if touched:
        if void_on_touch and policy == VOID_POLICY:
            return VOID
        return DISTURBED
    return CLEAN


def usable(verdict: str) -> bool:
    """Whether a consumer should count this number. `void` is the only outright no."""
    return verdict != VOID


# --- sealing -----------------------------------------------------------------------


def frame_hash(jpeg: bytes) -> str:
    return hashlib.sha256(jpeg).hexdigest()


def seal(jpeg: bytes | None, dice: list[Die]) -> str:
    """
    An identifier for this exact roll: the frame plus what was read from it.

    Two purposes. A game can log it and later point at which picture produced a number. And
    a repeat is meaningful: a real sensor never produces two byte-identical frames, so the
    same seal twice means a frozen feed or a replayed image, not luck.
    """
    payload = json.dumps(_multiset(dice), sort_keys=True).encode()
    digest = hashlib.sha256()
    digest.update(jpeg or b"")
    digest.update(payload)
    return f"sha256:{digest.hexdigest()[:32]}"
