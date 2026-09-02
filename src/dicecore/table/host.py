"""
The table: the instance that owns the game while other DiceCores play at it.

One host, several guests, one game. The host's `GameSession` is the only copy that matters;
guests mirror it and ask for things. That lopsidedness is the point — a turn-based game
played in three rooms needs exactly one answer to "whose turn is it", and the alternative is
two screens quietly disagreeing about who booked the full house.

Each player throws on *their own* DiceCore, with their own camera or their own simulator, and
sends the dice up. Nobody has to share a tower, which is the reason to play over a network
in the first place.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from typing import Any

from ..dice import Box, Die, RollResult
from . import protocol
from .protocol import Seat

#: How many people can sit down. More than eight is not a dice game, it is a queue.
MAX_SEATS = 8


def dice_from(payload: Any) -> list[Die]:
    """
    Rebuild the dice a guest reported.

    Their boxes are meaningless here — they are pixels in somebody else's picture — but the
    turn machine wants positions to work out what was held, so they are kept as sent. What
    is *not* trusted is anything else: a guest reports faces, not scores.
    """
    dice: list[Die] = []
    for raw in (payload or [])[:12]:
        if not isinstance(raw, dict):
            continue
        box = raw.get("box") or {}
        dice.append(Die(
            kind=str(raw.get("kind", "d6"))[:5],
            value=int(raw.get("value", 0)),
            box=Box(int(box.get("x", 0)), int(box.get("y", 0)),
                    int(box.get("w", 40)), int(box.get("h", 40))),
            confidence=float(raw.get("confidence", 0.0)),
            colour=raw.get("colour"),
        ))
    return dice


class Table:
    """
    The host side. Owns the seats, applies what guests ask for, and tells everybody.

    Thread-safe because two worlds poke it: the asyncio side (guest sockets) and the reader's
    own thread (the host's dice landing). Both are rare and cheap, so one lock over the whole
    object is the right amount of machinery.
    """

    def __init__(self, reader: Any, name: str = "DiceCore") -> None:
        self.reader = reader
        self.name = name
        self.open = False
        self.seats: list[Seat] = []
        self.log: list[str] = []
        self._lock = threading.RLock()
        #: seat index → the websocket to send to. The host's own seat has none.
        self._sockets: dict[int, Any] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    # --- opening and closing ------------------------------------------------
    def start(self, host_player: str = "") -> dict[str, Any]:
        """Open the table, with the host taking the first seat."""
        with self._lock:
            self.open = True
            self.seats = [Seat(host_player or self.name, 0, remote=False)]
            self._sockets.clear()
            self._note(f"Table open — {self.seats[0].name} is seat 1.")
            self._sync_players()
            return self.describe()

    def stop(self) -> dict[str, Any]:
        with self._lock:
            self.open = False
            for socket in list(self._sockets.values()):
                self._send_soon(socket, protocol.note("The table has closed."))
            self._sockets.clear()
            self.seats = []
            self._note("Table closed.")
            return self.describe()

    # --- seats --------------------------------------------------------------
    def seat_for(self, name: str, socket: Any) -> tuple[int | None, str | None]:
        """Sit somebody down. Returns their seat, or why they cannot have one."""
        with self._lock:
            if not self.open:
                return None, "This DiceCore is not hosting a table."
            if len(self.seats) >= MAX_SEATS:
                return None, f"The table is full ({MAX_SEATS} seats)."
            # A guest who dropped and came back gets their own chair, not a new one — with
            # their scorecard still on it.
            for seat in self.seats:
                if seat.name == name and seat.remote and not seat.connected:
                    seat.connected = True
                    self._sockets[seat.index] = socket
                    self._note(f"{name} is back.")
                    self._sync_players()
                    return seat.index, None
            seat = Seat(name or f"Player {len(self.seats) + 1}", len(self.seats), remote=True)
            self.seats.append(seat)
            self._sockets[seat.index] = socket
            self._note(f"{seat.name} sat down as seat {seat.index + 1}.")
            self._sync_players()
            return seat.index, None

    def leave(self, index: int) -> None:
        with self._lock:
            self._sockets.pop(index, None)
            for seat in self.seats:
                if seat.index == index:
                    seat.connected = False
                    self._note(f"{seat.name} left.")
            self.broadcast()

    def _sync_players(self) -> None:
        """
        Put the seat names into the game.

        Changing the player list restarts a game, so this only ever runs while the table is
        being assembled — sitting down after the first throw would wipe the scorecard, and
        the seat that arrives late waits for the next game instead.
        """
        names = [seat.name for seat in self.seats]
        game = self.reader.game
        if game.running and len(names) != len(game.players):
            self._note("A seat changed mid-game — it takes effect in the next game.")
            return
        self.reader.settings.play.players = names
        game.players = names
        game.configure(game.mode, game.rules, names, keep_scores=game.running,
                       params=game.params)

    # --- what guests ask for -------------------------------------------------
    def apply(self, seat: int | None, message: dict[str, Any]) -> dict[str, Any] | None:
        """
        Do what a guest asked, or refuse it with a reason.

        Every refusal comes back as words rather than silence: a button that does nothing is
        the worst thing a game played at a distance can offer.
        """
        with self._lock:
            game = self.reader.game
            problem = protocol.check(message, seat, game.turn.player, game.running)
            if problem:
                return protocol.refused(problem, str(message.get("action", "")))
            if message.get("type") != "action":
                return None

            name = message["action"]
            try:
                self._do(name, message, game)
            except ValueError as exc:
                return protocol.refused(str(exc), name)
            self.broadcast()
            return None

    def _do(self, name: str, message: dict[str, Any], game: Any) -> None:
        if name == "roll":
            dice = dice_from(message.get("dice"))
            if not dice:
                raise ValueError("That roll had no dice in it.")
            result = RollResult(dice=dice, engine=str(message.get("engine", "remote"))[:24])
            self.reader.apply_mode(result)
            game.observe(result)
            self.reader.last_remote = result
        elif name == "hold":
            game.hold(int(message.get("index", -1)))
        elif name == "chip":
            game.chip()
        elif name == "book":
            game.book(str(message.get("category", "")), bool(message.get("cross_out")))
        elif name == "bank":
            game.bank()
        elif name == "aside":
            game.set_aside()
        elif name == "next":
            ok, problem = game.finish_turn()
            if not ok:
                raise ValueError(problem or "Cannot end the turn.")
        elif name == "undo":
            ok, problem = game.undo()
            if not ok:
                raise ValueError(problem or "Nothing to take back.")

    # --- telling everybody ---------------------------------------------------
    def broadcast(self) -> None:
        """Send the whole game to every guest. A few kilobytes; diffing would buy nothing
        but a class of bug where two screens quietly disagree."""
        with self._lock:
            if not self.open or not self._sockets:
                return
            last = self.reader.last
            payload = protocol.state(self.game_json(), self.seats,
                                     last.to_json() if last else None)
            for socket in list(self._sockets.values()):
                self._send_soon(socket, payload)

    def game_json(self) -> dict[str, Any]:
        """The game as guests see it, plus how many dice are wanted right now.

        Only the host knows the pool — in Farkle it shrinks as dice are set aside — and a
        guest throwing five when three are in hand would be inventing a roll."""
        game = self.reader.game.to_json()
        game["pool"] = self.reader.dice_wanted()
        return game

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Remember the server's event loop, so the reader's thread can send through it."""
        self._loop = loop

    def _send_soon(self, socket: Any, payload: dict[str, Any]) -> None:
        text = json.dumps(payload)

        async def deliver() -> None:
            try:
                await socket.send_text(text)
            except Exception:
                pass  # a guest that vanished is handled when its socket closes

        loop = self._loop
        if loop is None:
            return
        try:
            asyncio.run_coroutine_threadsafe(deliver(), loop)
        except RuntimeError:
            pass

    def _note(self, text: str) -> None:
        self.log.append(f"{time.strftime('%H:%M:%S')}  {text}")
        del self.log[:-20]

    def describe(self) -> dict[str, Any]:
        with self._lock:
            return {"open": self.open, "name": self.name,
                    "seats": [s.to_json() for s in self.seats],
                    "connected": len(self._sockets), "log": list(reversed(self.log)),
                    "max_seats": MAX_SEATS}
