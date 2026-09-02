"""
The guest side: this DiceCore playing at somebody else's table.

It keeps a websocket to the host, mirrors whatever game state arrives, and sends up the dice
that land on *this* tray when it is this player's turn. The local reader keeps doing exactly
what it always did — camera or simulator, settling, fair play — and the result goes up the
wire instead of only onto the local screen.

Reconnects on its own, because a game lasts an hour and a WiFi hiccup should cost a second
rather than an evening.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import threading
import time
from typing import Any

from . import protocol

#: Backing off, so a host that is restarting is not hammered by four guests.
RETRY_START_S = 1.0
RETRY_MAX_S = 20.0
#: How long Join waits for a first answer before letting the retry loop have it.
JOIN_WAIT_S = 3.0


def table_url(address: str) -> str:
    """
    Turn whatever somebody pasted into a websocket address.

    People paste `http://pi.local:8099/`, `pi.local`, or the whole setup URL. All three mean
    the same table, and refusing two of them would be pedantry.
    """
    text = (address or "").strip()
    if not text:
        return ""
    for prefix in ("http://", "https://", "ws://", "wss://"):
        if text.startswith(prefix):
            text = text[len(prefix):]
            break
    text = text.split("/")[0]
    if ":" not in text:
        text += ":8099"
    return f"ws://{text}/api/v1/table"


class Guest:
    """One connection to a host, run on its own thread with its own event loop."""

    def __init__(self, reader: Any, on_state: Any = None) -> None:
        self.reader = reader
        self.on_state = on_state
        self.address = ""
        self.name = ""
        self.seat: int | None = None
        self.connected = False
        self.problem: str | None = None
        self.game: dict[str, Any] | None = None
        #: Bumped every time the mirror changes. The browser on this instance watches this
        #: number rather than polling the host: the mirror is already here, in memory.
        self.revision = 0
        #: The address as somebody typed it, which is what the screen shows.
        self.typed = ""
        #: Set once the first attempt has either worked or failed, so that pressing Join
        #: with a typo in the address says so instead of spinning forever.
        self._settled = threading.Event()
        self.seats: list[dict[str, Any]] = []
        self.last_seen: float = 0.0
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._socket: Any = None
        self._stop = threading.Event()

    # --- lifecycle -----------------------------------------------------------
    def join(self, address: str, name: str) -> tuple[bool, str]:
        url = table_url(address)
        if not url:
            return False, "No address. Paste the other DiceCore's address, e.g. pi.local:8099"
        self.leave()
        self.address, self.name = url, (name or "Player")
        # What was typed, kept for the screen. Showing somebody "ws://…/api/v1/table" when
        # they entered "pi.local:8099" is technically true and useless.
        self.typed = address.strip()
        self.problem = None
        self._stop.clear()
        self._settled.clear()
        self._thread = threading.Thread(target=self._run, name="dicecore-guest", daemon=True)
        self._thread.start()
        # Wait out the first attempt rather than reporting success optimistically. After
        # this it retries in the background forever — a host that reboots mid-game is a
        # pause, not the end — but the first answer belongs to whoever pressed the button.
        self._settled.wait(JOIN_WAIT_S)
        if self.connected:
            return True, f"Joined {address}."
        if self.problem:
            # Never answered at all: almost always a typo, so stop rather than retry a
            # wrong address all evening. A host that drops *after* connecting is the other
            # case entirely, and that one is retried forever.
            problem = self.problem
            self.leave()
            self.problem = problem
            return False, f"{address} did not answer: {problem}"
        return True, f"Joining {address}… still trying."

    def leave(self) -> None:
        self._stop.set()
        loop, socket = self._loop, self._socket
        if loop is not None and socket is not None:
            with contextlib.suppress(Exception):
                asyncio.run_coroutine_threadsafe(socket.close(), loop)
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._thread = None
        self.connected = False
        self.seat = None
        self.game = None

    @property
    def active(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def dice_wanted(self) -> int:
        """How many dice to throw. The host says, because only the host is playing."""
        game = self.game or {}
        return int(game.get("pool") or 0)

    @property
    def my_turn(self) -> bool:
        game = self.game
        return bool(game and self.seat is not None
                    and game.get("running") and game["turn"]["player"] == self.seat)

    # --- sending -------------------------------------------------------------
    def send(self, message: dict[str, Any]) -> bool:
        """Queue a message for the host. False when there is nowhere to send it."""
        loop, socket = self._loop, self._socket
        if loop is None or socket is None or not self.connected:
            return False

        async def deliver() -> None:
            with contextlib.suppress(Exception):
                await socket.send(json.dumps(message))

        with contextlib.suppress(RuntimeError):
            asyncio.run_coroutine_threadsafe(deliver(), loop)
            return True
        return False

    def report_roll(self, result: Any) -> bool:
        """Send the dice that just landed on this tray up to the table."""
        if not self.connected:
            return False
        return self.send(protocol.action(
            "roll", engine=result.engine,
            dice=[{"kind": d.kind, "value": d.value, "confidence": d.confidence,
                   "colour": d.colour,
                   "box": {"x": d.box.x, "y": d.box.y, "w": d.box.w, "h": d.box.h}}
                  for d in result.dice]))

    # --- the connection ------------------------------------------------------
    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._connect_forever())
        finally:
            with contextlib.suppress(Exception):
                loop.close()
            self._loop = None

    async def _connect_forever(self) -> None:
        from websockets.asyncio.client import connect

        delay = RETRY_START_S
        while not self._stop.is_set():
            try:
                async with connect(self.address, open_timeout=8, ping_interval=20) as socket:
                    self._socket = socket
                    self.connected = True
                    self.problem = None
                    self._settled.set()
                    delay = RETRY_START_S
                    await socket.send(json.dumps(protocol.hello(self.name)))
                    async for raw in socket:
                        self._receive(raw)
            except Exception as exc:
                self.problem = str(exc)[:160]
                self._settled.set()
            finally:
                self.connected = False
                self._socket = None
            if self._stop.is_set():
                return
            # A game lasts an hour; a WiFi hiccup should cost a second, not an evening.
            await asyncio.sleep(delay)
            delay = min(delay * 2, RETRY_MAX_S)

    def _receive(self, raw: str | bytes) -> None:
        try:
            message = json.loads(raw)
        except ValueError:
            return
        kind = message.get("type")
        if kind == "welcome":
            problem = protocol.version_problem(message.get("version"))
            if problem:
                self.problem = problem
                self._stop.set()
                return
            self.seat = int(message.get("seat", 0))
            self.seats = message.get("seats") or []
            self.game = message.get("game")
        elif kind == "state":
            self.game = message.get("game")
            self.seats = message.get("seats") or []
            self.last_seen = time.time()
        elif kind in ("refused", "note"):
            self.problem = message.get("reason") or message.get("text")
        self.revision += 1
        if self.on_state:
            with contextlib.suppress(Exception):
                self.on_state(self)

    def describe(self) -> dict[str, Any]:
        return {"active": self.active, "connected": self.connected, "seat": self.seat,
                "address": self.typed or self.address, "url": self.address,
                "name": self.name, "problem": self.problem,
                "seats": self.seats, "my_turn": self.my_turn,
                "last_seen": self.last_seen, "revision": self.revision,
                # The mirrored game: the guest's screen has nothing else to draw. There is
                # no game on this instance while it is a guest, only somebody else's.
                "game": self.game}
