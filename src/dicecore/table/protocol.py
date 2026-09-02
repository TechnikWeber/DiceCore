"""
What one DiceCore says to another.

Every message is a small JSON object with a `type`. The shapes live here, apart from the
sockets, so that "what happens when a guest sends a roll out of turn" is a question the test
suite can answer without a network.

The model is deliberately lopsided: **one instance is the table and owns the game.** Guests
mirror its state and ask it to do things. Nobody merges anything, nobody resolves conflicts,
and there is exactly one answer to "whose turn is it" — which is the whole difficulty in a
turn-based game played in three rooms at once.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

#: Bumped when the shape changes in a way the other side cannot cope with. A guest and a
#: host on different versions are told so rather than left to misunderstand each other.
VERSION = 1

# --- what a guest may ask for -----------------------------------------------------

#: Actions a guest can send, and whether they are only for the player whose turn it is.
ACTIONS: dict[str, bool] = {
    "roll": True,        # "these are the dice I just threw"
    "hold": True,
    "chip": True,
    "book": True,
    "bank": True,
    "aside": True,
    "next": True,
    "undo": True,
    "leave": False,
    "hello": False,
    "ping": False,
}


@dataclass
class Seat:
    """One player at the table, and the connection they are on."""

    name: str
    index: int
    #: None for the host's own seat — it has no socket to itself.
    remote: bool = False
    joined: float = field(default_factory=time.time)
    connected: bool = True

    def to_json(self) -> dict[str, Any]:
        return {"name": self.name, "index": self.index, "remote": self.remote,
                "connected": self.connected, "joined": self.joined}


def hello(name: str, version: int = VERSION) -> dict[str, Any]:
    return {"type": "hello", "name": name, "version": version}


def welcome(seat: int, seats: list[Seat], game: dict[str, Any]) -> dict[str, Any]:
    return {"type": "welcome", "seat": seat, "version": VERSION,
            "seats": [s.to_json() for s in seats], "game": game}


def state(game: dict[str, Any], seats: list[Seat], last: dict[str, Any] | None = None
          ) -> dict[str, Any]:
    """The whole game, every time. A table's state is a few kilobytes and diffing it would
    buy nothing but a class of bug where two screens quietly disagree."""
    return {"type": "state", "game": game, "seats": [s.to_json() for s in seats],
            "last": last, "at": time.time()}


def action(name: str, **payload: Any) -> dict[str, Any]:
    return {"type": "action", "action": name, **payload}


def refused(reason: str, action_name: str = "") -> dict[str, Any]:
    return {"type": "refused", "reason": reason, "action": action_name}


def note(text: str) -> dict[str, Any]:
    return {"type": "note", "text": text}


# --- deciding whether to do it ----------------------------------------------------


def check(message: dict[str, Any], seat: int | None, current_player: int,
          running: bool) -> str | None:
    """
    Whether this message may be acted on. Returns the reason to refuse, or None.

    The rule that matters: **only the player whose turn it is may act.** Without it, two
    people pressing "book" at the same moment is a race for a scorecard box, and the loser
    finds out by seeing a number they did not choose.
    """
    if not isinstance(message, dict):
        return "That is not a message."
    if message.get("type") != "action":
        return None
    name = message.get("action")
    if name not in ACTIONS:
        return f"Unknown action {name!r}."
    if not ACTIONS[name]:
        # Saying hello, leaving, and answering a ping are nobody's turn in particular — and
        # a guest still waiting for a seat has to be able to do all three.
        return None
    if seat is None:
        return "You have no seat at this table yet."
    if not running:
        return "No game is running."
    if seat != current_player:
        return "It is not your turn."
    return None


def version_problem(theirs: Any) -> str | None:
    """A guest and a host on different versions are told, not left to misunderstand."""
    try:
        theirs = int(theirs)
    except (TypeError, ValueError):
        return "That DiceCore did not say which protocol version it speaks."
    if theirs != VERSION:
        return (f"That DiceCore speaks table protocol {theirs}, this one speaks {VERSION}. "
                f"Update the older one.")
    return None
