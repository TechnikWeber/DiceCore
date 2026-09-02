"""
Keeping a game across a restart.

An evening of Kniffel is an hour of somebody's life, and a Pi that loses power should not
cost it. The whole session is written to one small JSON file after every move that changes
anything, and read back when the service comes up.

Deliberately not a database and deliberately not clever: one file, rewritten whole, and a
file that cannot be read is a game that did not survive — never a service that will not
start. Losing a game is bad; losing the machine that reads the dice is worse.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import kniffel
from .farkle import FarkleState
from .session import GameSession, TurnRecord
from .turns import DieSlot, Turn, TurnRules

#: Bump when the shape changes in a way an older file cannot satisfy. A file from a
#: different version is dropped rather than half-understood.
VERSION = 1


def to_dict(session: GameSession) -> dict[str, Any]:
    turn = session.turn
    return {
        "version": VERSION,
        "mode": session.mode,
        "running": session.running,
        "players": list(session.players),
        "colours": list(session.colours),
        "params": dict(session.params),
        "chips": list(session.chips),
        "started": session.started,
        "reading": session.reading,
        "rules": {"rolls": session.rules.rolls, "holds": session.rules.holds,
                  "chips": session.rules.chips, "auto_end": session.rules.auto_end,
                  "unlimited": session.rules.unlimited},
        "turn": {"number": turn.number, "player": turn.player,
                 "rolls_used": turn.rolls_used, "rolls_allowed": turn.rolls_allowed,
                 "chips_left": turn.chips_left, "finished": turn.finished,
                 "spent": turn.spent, "unlimited": turn.unlimited,
                 "dice": [{"kind": d.kind, "value": d.value, "held": d.held,
                           "colour": d.colour, "x": d.x, "y": d.y, "size": d.size}
                          for d in turn.dice]},
        "cards": [{"name": c.name, "sheet": c.sheet.id, "scores": dict(c.scores)}
                  for c in session.cards],
        "farkle": (None if session.farkle is None else {
            "banked": list(session.farkle.banked), "turn_points": session.farkle.turn_points,
            "dice_left": session.farkle.dice_left, "farkled": session.farkle.farkled,
            "target": session.farkle.target, "entry": session.farkle.entry,
            "on_board": list(session.farkle.on_board)}),
        "log": [record.to_json() for record in session.log],
    }


def from_dict(data: dict[str, Any]) -> GameSession:
    """Rebuild a session. Raises on anything it cannot make sense of; the caller drops it."""
    if int(data.get("version", 0)) != VERSION:
        raise ValueError(f"game file is version {data.get('version')}, not {VERSION}")
    rules = TurnRules(**{k: data["rules"][k] for k in
                         ("rolls", "holds", "chips", "auto_end", "unlimited")})
    session = GameSession(str(data["mode"]), rules, list(data["players"]),
                          dict(data.get("params") or {}))
    return apply_dict(session, data)


def apply_dict(session: GameSession, data: dict[str, Any]) -> GameSession:
    """
    Pour a saved state back into a session that already exists.

    Needed twice: reading a game off disk at startup, and undoing a move — both are "make
    this session be that state again", and the reader holds one session object for the life
    of the process, so replacing it is not an option.
    """
    rules = TurnRules(**{k: data["rules"][k] for k in
                         ("rolls", "holds", "chips", "auto_end", "unlimited")})
    session.mode = str(data["mode"])
    session.rules = rules
    session.players = list(data["players"])
    session.params = dict(data.get("params") or {})
    session.colours = list(data.get("colours") or session.colours)
    session.chips = list(data.get("chips") or session.chips)
    session.started = float(data.get("started", session.started))
    session.reading = data.get("reading")
    session.running = bool(data.get("running", False))

    raw = data["turn"]
    session.turn = Turn(
        number=int(raw["number"]), player=int(raw["player"]),
        rolls_used=int(raw["rolls_used"]), rolls_allowed=int(raw["rolls_allowed"]),
        chips_left=int(raw["chips_left"]), finished=bool(raw["finished"]),
        spent=bool(raw.get("spent", False)), unlimited=bool(raw.get("unlimited", False)),
        dice=[DieSlot(d["kind"], int(d["value"]), bool(d["held"]), d.get("colour"),
                      int(d.get("x", 0)), int(d.get("y", 0)), int(d.get("size", 1)))
              for d in raw.get("dice", [])],
    )

    session.cards = []
    for card in data.get("cards") or []:
        sheet = kniffel.SHEETS.get(card.get("sheet", "standard"), kniffel.STANDARD)
        restored = kniffel.Card(card["name"], sheet)
        for category, score in (card.get("scores") or {}).items():
            if category in restored.scores:
                restored.scores[category] = score
        session.cards.append(restored)

    farkle = data.get("farkle")
    session.farkle = None if farkle is None else FarkleState(
        players=len(session.players), target=int(farkle["target"]),
        entry=int(farkle["entry"]), banked=list(farkle["banked"]),
        turn_points=int(farkle["turn_points"]), dice_left=int(farkle["dice_left"]),
        farkled=bool(farkle["farkled"]), on_board=list(farkle["on_board"]))

    session.log = [TurnRecord(int(r["player"]), int(r["number"]), list(r["values"]),
                              r.get("headline", ""), r.get("booked"), r.get("points"),
                              float(r.get("at", 0.0)))
                   for r in data.get("log") or []]
    return session


def save(session: GameSession, path: Path) -> None:
    """Write the game. Write-then-rename, so a power cut cannot leave half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(to_dict(session), indent=1))
    tmp.replace(path)


def load(path: Path) -> GameSession | None:
    """Read the game back, or None. Never raises — a lost game must not cost the service."""
    if not path.exists():
        return None
    try:
        return from_dict(json.loads(path.read_text()))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def clear(path: Path) -> None:
    path.unlink(missing_ok=True)
