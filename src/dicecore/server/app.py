"""
The HTTP surface.

Two audiences, kept apart on purpose:

* **`/api/v1/…`** is the contract other projects depend on — a game, a Discord bot, a
  scoreboard. It is small, it is versioned, and it changes only additively. Everything in
  docs/API.md is here and nothing else.
* **`/api/setup/…`** is the web UI's own back end. It may change freely; nothing outside
  this repo should touch it.

The whole page is one static HTML file served per request, and there is no build step. That
is what makes "git pull && systemctl restart" a complete update on a Pi over a bad link.
"""

# NOTE: deliberately no `from __future__ import annotations` in this module. FastAPI
# resolves parameter annotations with `get_type_hints` against the *module* globals, and
# the FastAPI symbols are imported inside `create_app` so this file stays importable
# without FastAPI. With postponed annotations, `request: Request` would resolve to nothing
# and every POST body would be rejected as a missing query parameter (422).

import asyncio
import contextlib
import json
import time
from pathlib import Path
from typing import Any

from .. import __version__
from ..capture import SOURCES, CaptureError, use_simulator
from ..config import Settings, config_path
from ..dataset import transfer
from ..dataset.store import DatasetStore
from ..dice import DIE_FACES, DIE_KINDS, values_for
from ..engine import MODES, EngineError
from ..install import EXTRAS, Installer, available
from ..integrity import POLICIES
from ..modes import DEFAULT as DEFAULT_MODE
from ..modes import MODES as GAME_MODES
from ..modes import mode_by_id
from ..modes.catalogue import rules_for
from ..panel import ButtonPanel, OutputHub
from ..panel import state as phases
from ..panel.displays import COMMON_SIZES, PANELS
from ..reader import Reader
from ..system import boot_config, diagnostics
from ..system.network import HotspotProfile, Network, is_country_code
from ..system.portal import CaptivePortal, Watcher, auto_hotspot_wanted
from ..table import Guest, Table, addresses
from ..training import TrainingManager
from ..training.data import readiness

WEB_DIR = Path(__file__).parent / "web"


def create_app(settings: Settings | None = None) -> Any:
    try:
        from fastapi import FastAPI, File, HTTPException, Request, UploadFile, WebSocket
        from fastapi.responses import (
            HTMLResponse,
            JSONResponse,
            Response,
            StreamingResponse,
        )
    except ImportError as exc:  # pragma: no cover - depends on the install
        raise RuntimeError(
            "The server needs FastAPI: `pip install 'dicecore[server]'`."
        ) from exc

    loaded, complaints = Settings.load() if settings is None else (settings, [])
    state: dict[str, Any] = {"settings": loaded, "complaints": complaints, "hub": None,
                             #: Why the chosen dice source would not open, in the words the
                             #: switch on the game screen prints.
                             "dice_problem": None}
    hub = OutputHub(loaded.panel)
    state["hub"] = hub
    table = Table(None, loaded.server.public_name)
    guest = Guest(None)

    def on_roll(result: Any) -> None:
        """A roll landed here. Tell whichever table this instance belongs to."""
        if table.open:
            table.broadcast()
        elif guest.connected and guest.my_turn:
            # A tray that has not changed is not a throw. Locally the session refuses those
            # itself; a guest has to, or standing still would burn a throw on the host.
            if not result.stale:
                guest.report_roll(result)

    reader = Reader(loaded, on_phase=lambda p: state["hub"].update(p), on_roll=on_roll)
    table.reader = reader
    guest.reader = reader
    # Every change to the host's game reaches the guests, not only the ones they asked for.
    reader.game.listeners.append(lambda _: table.broadcast())
    state["table"] = table
    state["guest"] = guest
    training = TrainingManager(loaded)

    def on_chip() -> None:
        reader.game.chip()

    def on_next() -> None:
        """
        The panel's second button, and what it means depends on where you are.

        In the lobby it starts the configured game — which is the whole keyboard-free path:
        walk up, press one button, play. In a game it ends the turn, and refuses to where a
        decision is owed rather than quietly costing somebody their throw.
        """
        if not reader.game.running:
            mode = mode_by_id(state["settings"].mode.active)
            if mode is not None:
                params = state["settings"].mode.params.get(mode.id) or {}
                reader.game.start(mode.id, rules_for(mode, params),
                                  list(state["settings"].play.players),
                                  list(state["settings"].play.colours), params)
            return
        reader.game.finish_turn()

    buttons = ButtonPanel(loaded.panel.signals, on_chip, on_next)
    state["buttons"] = buttons

    @contextlib.asynccontextmanager
    async def lifespan(_: Any) -> Any:
        # The reader runs on its own thread and needs the server's event loop to push state
        # to guests at the table; this is the only place it can be got hold of.
        table.bind_loop(asyncio.get_running_loop())
        yield
        table.stop()
        guest.leave()

    # From the package, never written out here: a second copy of the version drifts,
    # and it drifted — `/health` reported 0.13.0 out of a 0.14.0 install.
    app = FastAPI(title="DiceCore", version=__version__,
                  description="Reads real dice with a camera.", lifespan=lifespan)
    app.state.reader = reader
    app.state.training = training
    app.state.hub = hub
    app.state.buttons = buttons
    installer = Installer()
    state["installer"] = installer

    # The network, and the watcher that opens the box's own when there is none. Started
    # here because a box that cannot be reached is exactly the one that has to fix itself.
    network = Network(loaded.network.interface)
    portal = CaptivePortal(loaded.server.port)
    watcher = Watcher(network, portal,
                      HotspotProfile(loaded.network.hotspot_ssid,
                                     loaded.network.hotspot_password),
                      loaded.network.grace_s)
    state["network"] = network
    state["watcher"] = watcher
    # Only where it belongs: see `auto_hotspot_wanted`. A development machine must not have
    # its WiFi taken over because a router hiccupped.
    if auto_hotspot_wanted(loaded.network.auto_hotspot, diagnostics.pi_model() is not None):
        watcher.start()
    app.state.network = network
    app.state.table = table
    app.state.guest = guest



    def store() -> DatasetStore:
        # The printing style travels with the store: it decides which labels are legal.
        return DatasetStore(state["settings"].dataset_dir, state["settings"].mode.d10_style)

    def fail(exc: Exception, code: int = 503) -> Any:
        """Errors are for humans: the UI prints `detail` verbatim, so it must be a sentence."""
        return JSONResponse({"error": type(exc).__name__, "detail": str(exc)}, status_code=code)

    def decode(payload: bytes) -> Any:
        import cv2
        import numpy as np

        image = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise HTTPException(400, "That upload is not a decodable image.")
        return image

    # --- the versioned, embeddable API ------------------------------------------------

    @app.get("/api/v1/stream.mjpg")
    def stream() -> Any:
        """
        A live view of the tray, for playing with people who are not in the room.

        It never opens the camera a second time. What it sends is whatever the reader last
        captured — so during a game it runs at the pace the dice are being read, and it
        cannot compete with the reading for the device. When nothing is being read it takes
        its own frames, slowly, because somebody watching a blank rectangle is being told
        nothing.

        Off unless switched on: a continuous view of whatever the camera can see is a
        different proposition from the single still the setup page asks for, and it is the
        room's decision rather than a default.
        """
        if not state["settings"].server.stream_enabled:
            return JSONResponse(
                {"error": "StreamDisabled",
                 "detail": "The live view is switched off. Turn it on under Setup → Camera "
                           "if you want people outside the room to watch the tray."},
                status_code=403)

        boundary = "dicecoreframe"
        interval = 1.0 / max(1, min(15, state["settings"].server.stream_fps))

        def frames() -> Any:
            last = None
            while True:
                jpeg = reader.last_jpeg()
                if jpeg is None or (not reader.game.running and jpeg is last):
                    try:
                        jpeg = reader.preview_jpeg()
                    except Exception:
                        time.sleep(interval)
                        continue
                if jpeg is not None and jpeg is not last:
                    last = jpeg
                    yield (f"--{boundary}\r\nContent-Type: image/jpeg\r\n"
                           f"Content-Length: {len(jpeg)}\r\n\r\n").encode() + jpeg + b"\r\n"
                time.sleep(interval)

        return StreamingResponse(
            frames(), media_type=f"multipart/x-mixed-replace; boundary={boundary}",
            headers={"Cache-Control": "no-store"})

    @app.get("/api/v1/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "name": state["settings"].server.public_name,
                "version": app.version, "at": time.time(),
                "stream": state["settings"].server.stream_enabled}

    @app.get("/api/v1/modes")
    def modes() -> Any:
        """
        The game modes and what each one expects. Part of the versioned API, because a
        consumer that offers a mode picker needs the same list DiceCore has.
        """
        return {
            "active": state["settings"].mode.active,
            "d10_style": state["settings"].mode.d10_style,
            "modes": [
                {"id": m.id, "label": m.label, "blurb": m.blurb, "kinds": list(m.kinds),
                 "dice": m.dice, "rule": m.rule, "stateful": m.stateful,
                 "family": m.family, "defaults": m.defaults,
                 "params": state["settings"].mode.params.get(m.id, {})}
                for m in GAME_MODES
            ],
        }

    @app.get("/api/v1/game")
    def game_state() -> Any:
        """
        Whose turn it is, how many throws are left, and what has been scored.

        Part of the versioned API because a play screen is exactly the sort of thing someone
        will want to write their own version of — on a tablet, on a TV, in a language this
        project does not use.
        """
        return {"game": reader.game.to_json(),
                "last": reader.last.to_json() if reader.last else None,
                "buttons": state["buttons"].describe(),
                "can_throw": reader.can_throw()}

    @app.post("/api/v1/game/hold")
    async def game_hold(request: Request) -> Any:
        """Correct which dice are being kept — the one thing the camera has to guess."""
        body = await request.json()
        reader.game.hold(int(body.get("index", -1)))
        return reader.game.to_json()

    @app.post("/api/v1/game/chip")
    def game_chip() -> Any:
        """Spend a chip for one more throw. The same call the GPIO button makes."""
        problem = reader.game.chip()
        return {"ok": problem is None, "detail": problem, "game": reader.game.to_json()}

    @app.post("/api/v1/game/book")
    async def game_book(request: Request) -> Any:
        """Score the dice into a category and hand the tower on."""
        body = await request.json()
        try:
            outcome = reader.game.book(str(body.get("category", "")),
                                       bool(body.get("cross_out", False)))
        except ValueError as exc:
            return fail(exc, 400)
        return {"ok": True, **outcome, "game": reader.game.to_json()}

    @app.post("/api/v1/game/aside")
    def game_set_aside() -> Any:
        """Farkle: take the held dice off the tray and put their points into the turn."""
        try:
            outcome = reader.game.set_aside()
        except ValueError as exc:
            return fail(exc, 400)
        return {**outcome, "game": reader.game.to_json()}

    @app.post("/api/v1/game/bank")
    def game_bank() -> Any:
        """Farkle: take what the turn has earned and hand the tower on."""
        try:
            outcome = reader.game.bank()
        except ValueError as exc:
            return fail(exc, 400)
        return {**outcome, "game": reader.game.to_json()}

    @app.post("/api/v1/game/undo")
    def game_undo() -> Any:
        """
        Take back the last booking, bank or ended turn — one step.

        A misclick on a scorecard costs that box for the rest of the game, which is the most
        expensive mistake the interface allows and the easiest one to make.
        """
        ok, problem = reader.game.undo()
        if not ok:
            return fail(RuntimeError(problem or "Nothing to take back."), 409)
        return reader.game.to_json()

    @app.post("/api/v1/game/next")
    def game_next() -> Any:
        """
        End the turn without booking anything. The same call the GPIO button makes.

        Only meaningful where "done" is the whole story — Backgammon, Mäxchen, and anything
        else where you move your own pieces and DiceCore has nothing to write down. A game
        with a scorecard refuses: there, ending a turn without booking would throw it away.
        """
        last = reader.last
        headline = (last.reading or {}).get("headline", "") if last else ""
        ok, problem = reader.game.finish_turn(headline)
        if not ok:
            return JSONResponse({"error": "DecisionOwed", "detail": problem,
                                 "game": reader.game.to_json()}, status_code=409)
        return reader.game.to_json()

    @app.post("/api/v1/game/start")
    async def game_start(request: Request) -> Any:
        """
        Begin a game: which one, who is playing, and the numbers it needs.

        The only way into a game, and deliberately so. Before this call nothing reads the
        tray — a camera quietly capturing for nobody is what made the game screen impossible
        to understand.
        """
        body = await request.json() if await request.body() else {}
        wanted = str(body.get("mode", state["settings"].mode.active))
        mode = mode_by_id(wanted)
        if mode is None:
            raise HTTPException(400, f"Unknown game mode {wanted!r}.")

        names = [str(n)[:24].strip() or f"Player {i + 1}"
                 for i, n in enumerate(body.get("players") or [])][:8]
        if not names:
            names = list(state["settings"].play.players) or ["Player 1", "Player 2"]
        colours = [str(c)[:9] for c in (body.get("colours") or [])][:len(names)]
        params = dict(state["settings"].mode.params.get(wanted) or {})
        if isinstance(body.get("params"), dict):
            params.update(body["params"])

        current = state["settings"]
        current.mode.active = wanted
        current.mode.params[wanted] = params
        current.play.players = names
        current.play.colours = colours
        current.save()
        reader.settings = current
        reader.game.start(wanted, rules_for(mode, params), names, colours, params)
        return reader.game.to_json()

    @app.post("/api/v1/game/stop")
    def game_stop() -> Any:
        """Back to the game picker. Reading stops with it."""
        reader.game.stop()
        return reader.game.to_json()

    @app.post("/api/v1/game/reset")
    async def game_reset(request: Request) -> Any:
        """Start over — new cards, first player, turn one."""
        body = await request.json() if await request.body() else {}
        players = body.get("players")
        if isinstance(players, list) and players:
            current = state["settings"]
            current.play.players = [str(p)[:24] for p in players][:8]
            current.save()
            reader.settings = current
            reader.configure_game()
        reader.game.reset()
        return reader.game.to_json()

    @app.get("/api/v1/roll")
    def roll(wait: int = 1, store_to: str = "", verify: int | None = None,
             mode: str = "") -> Any:
        """
        Read the dice now. `wait=1` waits for them to settle first.

        With fair play on, this call also **blocks for `guard.hold_s` while the tray is
        watched** — that wait is what the `verdict` is worth. `verify=0` answers immediately
        with `verdict: "pending"` instead; `/api/v1/verify` collects the verdict afterwards.

        `store_to=<set id>` files the frame into a dataset in the same call — that is how
        the label loop collects without a second capture, and how a consumer can contribute
        training data just by asking for rolls.

        `mode=<id>` reads this roll as that game without changing the configured one, so a
        bot counting successes and a screen showing a total can share one tray.
        """
        if mode and mode_by_id(mode) is None:
            raise HTTPException(400, f"Unknown game mode {mode!r}. See /api/v1/modes.")
        try:
            result = reader.read(wait_for_still=bool(wait),
                                 verify=None if verify is None else bool(verify))
            if mode:
                reader.apply_mode(result, mode)
        except (CaptureError, EngineError) as exc:
            return fail(exc)
        if store_to:
            jpeg = reader.last_jpeg()
            if jpeg:
                try:
                    sample = store().add_sample(store_to, jpeg, result, source="roll")
                    result.frame_id = sample.id
                except (FileNotFoundError, OSError) as exc:
                    result.warnings.append(f"Not stored: {exc}")
        return result.to_json()

    @app.post("/api/v1/verify")
    def verify_last() -> Any:
        """
        Finish judging the last roll: watch the tray, then answer with the verdict.

        For a caller that took the number immediately with `verify=0` and wants to know
        afterwards whether it still stands.
        """
        try:
            return reader.verify_last().to_json()
        except (CaptureError, EngineError) as exc:
            return fail(exc)

    @app.post("/api/v1/throw")
    def throw() -> Any:
        """
        Roll simulated dice and read them — the button on the play screen.

        Only the simulator can do this. A camera cannot: the dice on its tray are the ones
        somebody threw, and no amount of asking changes them.
        """
        try:
            # A guest has no game of its own to ask, so the pool and what is being kept
            # back both come down from the host.
            if guest.connected:
                return reader.throw(guest.dice_wanted, guest.held_now).to_json()
            return reader.throw().to_json()
        except (CaptureError, EngineError) as exc:
            return fail(exc, 400)

    @app.get("/api/v1/state")
    def last_state() -> Any:
        last = reader.last
        return last.to_json() if last else {"dice": [], "total": 0, "count": 0,
                                            "notation": "no dice", "engine": "none",
                                            "verdict": "unverified", "usable": True}

    @app.post("/api/v1/detect")
    async def detect(image: UploadFile = File(...)) -> Any:
        """
        Read an image someone else captured.

        This is the endpoint `engine.mode=remote` talks to, so it is the seam that lets a
        Pi Zero use a PC's engine — and it is also just a useful way to test the engine on
        a photograph.
        """
        payload = await image.read()
        try:
            return reader.read_image(decode(payload), source_name="detect").to_json()
        except (EngineError, CaptureError) as exc:
            return fail(exc)

    @app.post("/api/v1/frame")
    async def push_frame(image: UploadFile = File(...)) -> Any:
        """Accept a frame from a capture-only agent (capture.source=push)."""
        from ..dice import Frame

        payload = await image.read()
        reader.push.offer(Frame(image=decode(payload), jpeg=payload, source="push"))
        return {"ok": True}

    def dice_view() -> Any:
        """Which dice this DiceCore is playing with — the switch on the game screen."""
        capture = state["settings"].capture
        return {"simulated": capture.source == "sim", "source": capture.source,
                "camera_source": capture.camera_source,
                "can_throw": reader.can_throw(),
                "problem": state["dice_problem"]}

    @app.get("/api/v1/dice")
    def dice_status() -> Any:
        return dice_view()

    @app.post("/api/v1/dice")
    async def dice_switch(request: Request) -> Any:
        """
        Switch between real dice and simulated ones.

        On the game screen rather than buried in Setup on purpose: which dice you are
        playing with is a decision you make at the table, not a setting you configure once.
        Somebody who has never opened Setup should be able to play without finding it.
        """
        body = await request.json()
        settings = state["settings"]
        use_simulator(settings.capture, bool(body.get("simulated")),
                      diagnostics.pi_model() is not None)
        settings.save()
        reader.reload(settings)
        # Open it now rather than at the first throw: pressing "real dice" on a box with no
        # camera should say so immediately, while the person is still looking at the switch.
        state["dice_problem"] = None
        try:
            reader.source()
        except Exception as exc:
            state["dice_problem"] = str(exc)
        return dice_view()

    def table_view() -> Any:
        """Whether this DiceCore is hosting a table, sitting at one, or neither."""
        # Every address another machine could reach this one at, not the configured one:
        # `localhost` is the single address guaranteed not to work for the other players.
        reachable = addresses(state["settings"].server.port)
        return {"hosting": table.describe(), "guest": guest.describe(),
                "can_throw": reader.can_throw(),
                "name": state["settings"].server.public_name,
                "address": reachable[0] if reachable else "",
                "addresses": reachable}

    @app.get("/api/v1/table")
    def table_status() -> Any:
        return table_view()

    @app.post("/api/v1/table/host")
    async def table_host(request: Request) -> Any:
        """
        Open a table other DiceCores can play at.

        This instance owns the game from here on: guests mirror it and ask it for things.
        One answer to "whose turn is it" is the whole difficulty of a turn-based game played
        in three rooms, and one owner is how it is had.
        """
        body = await request.json() if await request.body() else {}
        if guest.active:
            guest.leave()
        return table.start(str(body.get("name", "") or "").strip()[:24])

    @app.post("/api/v1/table/close")
    def table_close() -> Any:
        return table.stop()

    @app.post("/api/v1/table/join")
    async def table_join(request: Request) -> Any:
        """Sit down at somebody else's table. Their game, your dice."""
        body = await request.json()
        if table.open:
            table.stop()
        ok, message = guest.join(str(body.get("address", "")),
                                 str(body.get("name", "") or "").strip()[:24])
        if not ok:
            return fail(RuntimeError(message), 400)
        return {"ok": True, "detail": message, "guest": guest.describe()}

    @app.post("/api/v1/table/leave")
    def table_leave() -> Any:
        guest.leave()
        return guest.describe()

    @app.post("/api/v1/table/act")
    async def table_act(request: Request) -> Any:
        """
        Do something at the table this instance is a guest at.

        The guest's screen cannot touch its own game — there is no game here, only a mirror
        of somebody else's — so every button goes through this.
        """
        body = await request.json()
        name = str(body.get("action", ""))
        payload = {k: v for k, v in body.items() if k != "action"}
        if not guest.connected:
            return fail(RuntimeError("Not connected to a table."), 409)
        from ..table import protocol as table_protocol

        if not guest.send(table_protocol.action(name, **payload)):
            return fail(RuntimeError("The message could not be sent."), 503)
        return {"ok": True}

    @app.websocket("/api/v1/table")
    async def table_socket(socket: WebSocket) -> None:
        """
        A guest's connection. One socket, one seat, until they leave.

        Everything a guest may ask for goes through `protocol.check` first, and every refusal
        comes back as words: a button that does nothing is the worst thing a game played at a
        distance can offer.
        """
        await socket.accept()
        table.bind_loop(asyncio.get_running_loop())
        seat: int | None = None
        try:
            while True:
                message = json.loads(await socket.receive_text())
                if message.get("type") == "hello":
                    from ..table import protocol as table_protocol

                    problem = table_protocol.version_problem(message.get("version"))
                    if problem:
                        await socket.send_text(json.dumps(table_protocol.refused(problem)))
                        return
                    seat, refusal = table.seat_for(str(message.get("name", ""))[:24], socket)
                    if seat is None:
                        await socket.send_text(json.dumps(table_protocol.refused(refusal or "")))
                        return
                    await socket.send_text(json.dumps(table_protocol.welcome(
                        seat, table.seats, table.game_json())))
                    table.broadcast()
                    continue
                answer = table.apply(seat, message)
                if answer is not None:
                    await socket.send_text(json.dumps(answer))
        except Exception:
            pass
        finally:
            if seat is not None:
                table.leave(seat)

    @app.websocket("/api/v1/events")
    async def events(socket: WebSocket) -> None:
        """
        Push every new result as it happens.

        Polling `/roll` would capture on every poll; this reads on its own schedule and
        emits only when the result actually changes, which is what a bot wants.
        """
        await socket.accept()
        previous: str | None = None
        seen: int | None = None
        try:
            while True:
                # Re-asked every pass: switching the source in Setup must take effect on the
                # screen that is already open, not at the next reload.
                camera = not reader.can_throw()
                if guest.active:
                    # Sitting at somebody else's table: there is no game on this instance to
                    # read, only their mirror of one. It changes when they move, so the
                    # screen follows the mirror rather than the tray. Cheap — it is already
                    # in memory here, so this watches a counter instead of asking the host.
                    if guest.revision != seen or previous is None:
                        seen = guest.revision
                        previous = ""
                        await socket.send_text(json.dumps({
                            "idle": not guest.my_turn, "manual": not camera, "away": True,
                            "game": guest.game, "table": table_view(),
                            "dice": dice_view()}))
                    if camera and guest.my_turn:
                        # A guest with a real tower throws real dice on their own turn, and
                        # `on_roll` sends what landed up to the host. Only on their turn:
                        # nobody else's camera should be running during your throw.
                        try:
                            await asyncio.to_thread(reader.read, True, False)
                        except (CaptureError, EngineError) as exc:
                            await socket.send_text(json.dumps({"error": str(exc)}))
                            await asyncio.sleep(2.0)
                        continue
                    await asyncio.sleep(0.2)
                    continue
                if not camera:
                    # A simulator throws when somebody presses the button, never because it
                    # was looked at. Polling one would be a random number generator with a
                    # picture attached — so this watches the game instead of the tray, and
                    # sends only when it actually changed. Quarter of a second because a
                    # guest's move has to appear on the host's screen while they are still
                    # looking at it.
                    payload = json.dumps({"idle": not reader.game.running, "manual": True,
                                          "table": table_view(), "dice": dice_view(),
                                          "game": reader.game.to_json()}, sort_keys=True)
                    if payload != previous:
                        previous = payload
                        await socket.send_text(payload)
                    await asyncio.sleep(0.25)
                    seen = None
                    continue
                if not reader.game.running:
                    # Nothing is being played, so nothing is looked at. This is what makes
                    # the lobby honest — and it is also why the Pi is not capturing all
                    # night for an empty table.
                    await socket.send_text(json.dumps({"idle": True,
                                                       "table": table_view(),
                                                       "dice": dice_view(),
                                                       "game": reader.game.to_json()}))
                    await asyncio.sleep(1.0)
                    previous = None
                    seen = None
                    continue
                try:
                    # Two messages per roll on purpose: the number as soon as the dice
                    # settle (`verdict: "pending"`), then the same roll again once the tray
                    # has been watched. A scoreboard uses the first; anything that must not
                    # honour a tampered roll waits for the second.
                    result = await asyncio.to_thread(reader.read, True, False)
                    body = result.to_json()
                    # Additive: consumers reading `total` and `dice` are untouched, and a
                    # play screen gets the turn state in the same message as the number.
                    body["game"] = reader.game.to_json()
                    body["table"] = table_view()
                    body["dice"] = dice_view()
                    payload = json.dumps(body, sort_keys=True)
                    if payload != previous:
                        previous = payload
                        await socket.send_text(payload)
                        if state["settings"].guard.enabled:
                            verified = await asyncio.to_thread(reader.verify_last)
                            after = verified.to_json()
                            after["game"] = reader.game.to_json()
                            after["table"] = table_view()
                            after["dice"] = dice_view()
                            previous = json.dumps(after, sort_keys=True)
                            await socket.send_text(previous)
                except (CaptureError, EngineError) as exc:
                    await socket.send_text(json.dumps({"error": str(exc)}))
                    await asyncio.sleep(2.0)
                await asyncio.sleep(0.4)
        except Exception:
            # A disconnecting client is normal and must not be logged as a failure.
            return

    # --- the setup page's own back end -----------------------------------------------

    @app.get("/api/setup/status")
    def status() -> Any:
        caps = diagnostics.probe()
        boot_state, boot_path = boot_config.read_boot_state()
        return {
            "reader": reader.status(),
            "complaints": state["complaints"],
            "capabilities": {
                "machine": caps.machine, "pi": caps.pi, "numpy": caps.numpy,
                "opencv": caps.opencv, "onnxruntime": caps.onnxruntime, "torch": caps.torch,
                "picamera2": caps.picamera2, "can_run_classic": caps.can_run_classic,
                "can_run_model": caps.can_run_model, "can_train": caps.can_train,
                "advice": caps.advice(),
            },
            "outputs": state["hub"].describe(),
            "boot": {"auto_detect": boot_state.auto_detect, "overlay": boot_state.overlay,
                     "module": boot_config.module_id_for(boot_state),
                     "path": str(boot_path) if boot_path else None},
            "config_path": str(config_path()),
        }

    @app.get("/api/setup/options")
    def options() -> Any:
        """Everything the UI needs to render its dropdowns, so it hardcodes nothing."""
        return {
            "sources": [{"id": i, "label": name} for i, name in SOURCES],
            "engines": [{"id": i, "label": name} for i, name in MODES],
            "csi_modules": [
                {"id": m.id, "label": m.label, "overlay": m.overlay, "note": m.note,
                 "tuning_file": m.tuning_file, "focus": m.focus}
                for m in boot_config.CSI_MODULES
            ],
            "kinds": [{"id": k, "faces": DIE_FACES[k],
                       "values": values_for(k, state["settings"].mode.d10_style)}
                      for k in DIE_KINDS],
            "modes": [{"id": m.id, "label": m.label, "blurb": m.blurb, "dice": m.dice,
                       "kinds": list(m.kinds), "rule": m.rule, "stateful": m.stateful,
                       "family": m.family, "defaults": m.defaults} for m in GAME_MODES],
            "default_mode": DEFAULT_MODE,
            "policies": [{"id": i, "label": name} for i, name in POLICIES],
            "panels": [{"id": i, "label": label, "mono": mono, "bus": bus,
                        "sizes": [list(s) for s in COMMON_SIZES.get(i, ())]}
                       for i, (label, _default, mono, bus) in PANELS.items()],
            "phases": list(phases.PHASES),
        }

    @app.post("/api/setup/mode")
    async def set_mode(request: Request) -> Any:
        """Switch the game, and adjust its numbers. Saved, so it survives a restart."""
        body = await request.json()
        current = state["settings"]
        wanted = str(body.get("mode", current.mode.active))
        if mode_by_id(wanted) is None:
            raise HTTPException(400, f"Unknown game mode {wanted!r}.")
        current.mode.active = wanted
        if isinstance(body.get("params"), dict):
            current.mode.params[wanted] = body["params"]
        if body.get("d10_style") in ("0-9", "1-10"):
            current.mode.d10_style = body["d10_style"]
        if "d10_zero_counts_as_ten" in body:
            current.mode.d10_zero_counts_as_ten = bool(body["d10_zero_counts_as_ten"])
        current.save()
        reader.reload(current)
        reader.settings = current
        reader.configure_game()
        return {"ok": True, "mode": wanted, "params": current.mode.params.get(wanted, {}),
                "d10_style": current.mode.d10_style,
                "d10_zero_counts_as_ten": current.mode.d10_zero_counts_as_ten}

    @app.post("/api/setup/mode/reset")
    def reset_mode_session() -> Any:
        """Start the fairness tally (or an open exploding roll) again from nothing."""
        reader.mode_sessions.pop(state["settings"].mode.active, None)
        return {"ok": True}

    @app.get("/api/setup/settings")
    def get_settings() -> Any:
        return state["settings"].to_dict()

    @app.put("/api/setup/settings")
    async def put_settings(request: Request) -> Any:
        body = await request.json()
        updated = Settings.from_dict(body)
        updated.save()
        state["settings"] = updated
        # The camera may have been changed from the other page; the switch on the game
        # screen must not keep printing a complaint about a source nobody uses any more.
        state["dice_problem"] = None
        reader.reload(updated)
        reader.settings = updated
        training.settings = updated
        # Rebuild the outputs: a changed pin or panel means new hardware to open, and the
        # old hub is holding the pins the new one wants.
        old = state["hub"]
        state["hub"] = OutputHub(updated.panel)
        old.close()
        app.state.hub = state["hub"]
        # The buttons hold pins too, and a changed pin needs the old one released first.
        state["buttons"].close()
        state["buttons"] = ButtonPanel(updated.panel.signals, on_chip, on_next)
        app.state.buttons = state["buttons"]
        watcher.profile = HotspotProfile(updated.network.hotspot_ssid,
                                         updated.network.hotspot_password)
        watcher.grace_s = updated.network.grace_s
        if auto_hotspot_wanted(updated.network.auto_hotspot,
                               diagnostics.pi_model() is not None):
            watcher.start()
        return {"ok": True, "settings": updated.to_dict()}

    @app.get("/api/setup/network")
    def network_status() -> Any:
        """What the box is connected to, what it can see, and what it is doing about it."""
        return {**state["network"].status(), "watcher": state["watcher"].describe(),
                "settings": {
                    "auto_hotspot": state["settings"].network.auto_hotspot,
                    "is_pi": diagnostics.pi_model() is not None,
                    "grace_s": state["settings"].network.grace_s,
                    "hotspot_ssid": state["settings"].network.hotspot_ssid,
                    "hotspot_open": not state["settings"].network.hotspot_password,
                    "captive_portal": state["settings"].network.captive_portal}}

    @app.post("/api/setup/network/scan")
    def network_scan() -> Any:
        """What is in range. Takes a couple of seconds — the radio has to go and look."""
        return {"networks": state["network"].scan()}

    @app.post("/api/setup/network/join")
    async def network_join(request: Request) -> Any:
        """
        Join a network.

        The answer arrives *before* the switch completes, because completing it takes the
        connection you are reading this over away with it — that is what having one radio
        means, and the page says so rather than appearing to hang.
        """
        body = await request.json()
        ok, message = state["network"].join(str(body.get("ssid", "")),
                                            str(body.get("password", "")))
        return {"ok": ok, "detail": message, "status": state["network"].status()}

    @app.post("/api/setup/network/hotspot")
    async def network_hotspot(request: Request) -> Any:
        """Open or close the box's own network by hand."""
        body = await request.json() if await request.body() else {}
        current = state["settings"]
        if body.get("stop"):
            ok, message = state["network"].stop_hotspot()
            state["watcher"].portal.stop()
            return {"ok": ok, "detail": message}
        profile = HotspotProfile(str(body.get("ssid") or current.network.hotspot_ssid),
                                 str(body.get("password") or current.network.hotspot_password))
        ok, message = state["network"].start_hotspot(profile)
        if ok and current.network.captive_portal:
            state["watcher"].portal.start()
        return {"ok": ok, "detail": message}

    @app.post("/api/setup/network/country")
    async def network_country(request: Request) -> Any:
        """
        Set the WiFi country, which a Pi refuses to transmit without.

        The single most common reason a fresh Pi's hotspot never appears, and a sentence
        nobody guesses from nmcli's "device is not available".
        """
        body = await request.json()
        code = str(body.get("country", ""))
        if not is_country_code(code):
            raise HTTPException(400, f"{code!r} is not a two-letter country code.")
        ok, message = state["network"].set_country(code)
        return {"ok": ok, "detail": message}

    @app.get("/api/setup/hardware")
    def hardware() -> Any:
        report = diagnostics.detect_cameras()
        boot_state, _ = boot_config.read_boot_state()
        return {
            "tool": report.tool, "csi": report.csi, "video_nodes": report.video_nodes,
            "problem": report.problem,
            "boot_advice": boot_config.explain_boot_config(boot_state, len(report.csi)),
        }

    @app.post("/api/setup/camera-module")
    async def camera_module(request: Request) -> Any:
        """
        Write the chosen CSI module into config.txt. Needs a reboot to take effect.

        This is the one endpoint that changes whether the Pi boots, so it validates a custom
        overlay name against the shape dtoverlay accepts before writing anything.
        """
        body = await request.json()
        module_id = str(body.get("module", "auto"))
        module = boot_config.module_by_id(module_id)
        if module is None:
            raise HTTPException(400, f"Unknown camera module {module_id!r}.")
        overlay = module.overlay
        if module_id == "custom":
            overlay = str(body.get("overlay", "")).strip()
            if not boot_config.valid_overlay_name(overlay):
                raise HTTPException(400, f"{overlay!r} is not a valid overlay name.")
        try:
            path = boot_config.write_camera_module(overlay)
        except PermissionError:
            return JSONResponse(
                {"error": "PermissionError",
                 "detail": "Writing config.txt needs root. Run DiceCore as a service "
                           "(provisioning/install.sh) or apply the change with sudo."},
                status_code=403)
        except (FileNotFoundError, OSError) as exc:
            return fail(exc, 400)

        current = state["settings"]
        current.capture.csi_module = module_id
        if module.tuning_file:
            current.capture.tuning_file = module.tuning_file
        current.save()
        reader.reload(current)
        return {"ok": True, "path": str(path), "reboot_required": True,
                "note": module.note, "tuning_file": module.tuning_file}

    @app.get("/api/setup/preview.jpg")
    def preview() -> Any:
        try:
            return Response(reader.preview_jpeg(), media_type="image/jpeg",
                            headers={"Cache-Control": "no-store"})
        except (CaptureError, EngineError) as exc:
            return fail(exc)

    @app.get("/api/setup/frame.jpg")
    def last_frame() -> Any:
        jpeg = reader.last_jpeg()
        if jpeg is None:
            raise HTTPException(404, "Nothing has been read yet.")
        return Response(jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    # --- screen, lamps and buzzer -----------------------------------------------------

    @app.get("/api/setup/outputs")
    def outputs() -> Any:
        """What the screen is showing and what the lamps are doing, right now."""
        return state["hub"].describe()

    @app.get("/api/setup/display.png")
    def display_preview() -> Any:
        """
        Exactly what the little screen shows — whether or not one is attached.

        The preview is rendered for every panel, so the layout can be worked out on a laptop
        and checked against the real thing without a camera pointed at the tower.
        """
        display = state["hub"].display
        if display is None or display.last_png is None:
            raise HTTPException(404, "No display is enabled.")
        return Response(display.last_png, media_type="image/png",
                        headers={"Cache-Control": "no-store"})

    @app.post("/api/setup/outputs/test")
    async def outputs_test(request: Request) -> Any:
        """
        Walk through the phases so you can check the wiring without throwing anything.

        This is the endpoint you use with a screwdriver in hand: press it, watch the red
        lamp come on, hear the beep, watch it go green. A `phase` in the body shows just
        that one.
        """
        body = await request.json() if await request.body() else {}
        hub = state["hub"]
        if not hub.enabled:
            return fail(RuntimeError("Neither a display nor the lamps are enabled."), 409)

        wanted = str(body.get("phase", "")).strip()
        celebrate = bool(body.get("celebrate", True))
        if wanted:
            hub.update(phases.Presentation(
                phase=wanted, total=None if wanted == phases.IDLE else 20,
                notation="1d20 → 20", celebrate=celebrate))
            return {"ok": True, "phase": wanted}

        async def walk() -> None:
            for phase, pause in ((phases.ROLLING, 0.6), (phases.READING, 0.4),
                                 (phases.RESULT, 1.4), (phases.READY, 1.2)):
                hub.update(phases.Presentation(
                    phase=phase,
                    total=20 if phase in (phases.RESULT, phases.READY) else None,
                    notation="1d20 → 20",
                    celebrate=celebrate and phase in (phases.RESULT, phases.READY)))
                await asyncio.sleep(pause)
            hub.update(phases.Presentation(phase=phases.IDLE))

        asyncio.create_task(walk())
        return {"ok": True, "walking": True}

    # --- dataset ----------------------------------------------------------------------

    @app.get("/api/setup/sets")
    def list_sets() -> Any:
        return [{**s.to_json(), "stats": store().stats(s.id),
                 "readiness": readiness(store(), s.id).to_json()} for s in store().list_sets()]

    @app.post("/api/setup/sets/readiness")
    async def combined_readiness(request: Request) -> Any:
        """Whether these sets *together* can train a model — which is how training works."""
        body = await request.json()
        sets = [str(s) for s in (body.get("set_ids") or [])]
        if not sets:
            return {"total": 0, "classes": {}, "thin": [], "ready": False,
                    "reasons": ["Pick at least one set."]}
        try:
            return readiness(store(), sets).to_json()
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.post("/api/setup/sets")
    async def create_set(request: Request) -> Any:
        body = await request.json()
        record = store().create_set(str(body.get("name", "set")), str(body.get("note", "")))
        return record.to_json()

    @app.delete("/api/setup/sets/{set_id}")
    def delete_set(set_id: str) -> Any:
        try:
            store().delete_set(set_id)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        return {"ok": True}

    @app.get("/api/setup/sets/{set_id}/samples")
    def list_samples(set_id: str, limit: int = 50, unconfirmed_first: int = 1) -> Any:
        try:
            samples = list(store().iter_samples(set_id))
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        if unconfirmed_first:
            # The unconfirmed ones are the work; showing them first is what makes the loop
            # "roll, glance, correct, roll" instead of a scrolling exercise.
            samples.sort(key=lambda s: (s.confirmed, -s.at))
        else:
            samples.sort(key=lambda s: -s.at)
        return [s.to_json() for s in samples[:limit]]

    @app.post("/api/setup/sets/{set_id}/capture")
    def capture_into(set_id: str, wait: int = 1) -> Any:
        """Roll once and file the frame — the button the label loop is built around."""
        try:
            result = reader.read(wait_for_still=bool(wait))
        except (CaptureError, EngineError) as exc:
            return fail(exc)
        jpeg = reader.last_jpeg()
        if jpeg is None:
            raise HTTPException(503, "Could not encode the frame (is OpenCV installed?).")
        try:
            sample = store().add_sample(set_id, jpeg, result,
                                        source=state["settings"].capture.source)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        return {"sample": sample.to_json(), "result": result.to_json()}

    @app.post("/api/setup/sets/{set_id}/confirm-read")
    async def confirm_all_read(set_id: str, request: Request) -> Any:
        """
        Confirm every stored roll the engine read completely, as it read it.

        The label loop is mostly agreement: the engine has the pips right and the person is
        only there to say so. Two hundred d20 faces is two hundred clicks otherwise, and
        that is the evening that decides how good the model gets. Rolls with a die the
        engine could not read are left alone — those are the ones that need a person.
        """
        body = await request.json() if await request.body() else {}
        limit = int(body.get("limit", 200))
        try:
            samples = list(store().iter_samples(set_id))
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc

        confirmed = skipped = 0
        for sample in samples[:limit]:
            if sample.confirmed:
                continue
            if any(die.predicted is None or die.value == 0 for die in sample.dice) \
                    or not sample.dice:
                skipped += 1
                continue
            store().update_sample(set_id, sample.id,
                                  [{"kind": d.kind, "value": d.value} for d in sample.dice])
            confirmed += 1
        return {"confirmed": confirmed, "needs_you": skipped}

    @app.patch("/api/setup/sets/{set_id}/samples/{sample_id}")
    async def update_sample(set_id: str, sample_id: str, request: Request) -> Any:
        body = await request.json()
        try:
            sample = store().update_sample(set_id, sample_id, body.get("dice", []),
                                           body.get("note"))
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return sample.to_json()

    @app.delete("/api/setup/sets/{set_id}/samples/{sample_id}")
    def delete_sample(set_id: str, sample_id: str) -> Any:
        store().delete_sample(set_id, sample_id)
        return {"ok": True}

    @app.get("/api/setup/sets/{set_id}/export.zip")
    def export_set(set_id: str) -> Any:
        """
        The whole set as a zip: the frames, the labels, and its own description.

        For the case this exists for — a friend who owns the d20s collects a few hundred
        throws on his own tower and sends you a file — and for looking at your own data with
        the tools you already have.
        """
        try:
            payload = transfer.export_set(store(), set_id)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        return Response(payload, media_type="application/zip", headers={
            "Content-Disposition": f'attachment; filename="dicecore-{set_id}.zip"'})

    @app.post("/api/setup/sets/import")
    async def import_set(archive: UploadFile = File(...), name: str = "") -> Any:
        """Unpack an exported set into a new one of its own — never merged into another."""
        payload = await archive.read()
        try:
            return transfer.import_set(store(), payload, name)
        except (ValueError, KeyError) as exc:
            raise HTTPException(400, str(exc)) from exc
        except Exception as exc:
            return fail(exc, 400)

    @app.get("/api/setup/sets/{set_id}/samples/{sample_id}.jpg")
    def sample_frame(set_id: str, sample_id: str) -> Any:
        path = store().frame_path(set_id, sample_id)
        if not path.is_file():
            raise HTTPException(404, "No such frame.")
        return Response(path.read_bytes(), media_type="image/jpeg")

    # --- training ---------------------------------------------------------------------

    @app.get("/api/setup/training")
    def training_status() -> Any:
        ok, why = _torch_state()
        job = training.job
        return {"available": ok, "why": why, "job": job.to_json() if job else None,
                "models": _list_models(state["settings"]),
                "extras": available(), "can_install": bool(EXTRAS)}

    @app.get("/api/setup/publish")
    def publish_state() -> Any:
        """What is configured to receive rolls, and how the last few deliveries went."""
        return reader.publisher.describe()

    @app.post("/api/setup/publish/test")
    def publish_test() -> Any:
        """
        Send one made-up roll to everything that is switched on, and report what happened.

        A test that waits for the answer rather than firing and forgetting: the whole point
        is to find out whether the token is right, and "sent" is not that answer.
        """
        from ..dice import Box, Die, RollResult

        sample = RollResult(
            dice=[Die("d20", 17, Box(0, 0, 60, 60), 0.97),
                  Die("d6", 4, Box(80, 0, 50, 50), 0.99)],
            engine="test", verdict="clean")
        sample.reading = {"headline": "21", "detail": "4, 17 — a test from DiceCore",
                          "mode": "rpg"}
        attempts = reader.publisher.publish(sample, blocking=True)
        if not attempts:
            return fail(RuntimeError(
                "Nothing is switched on to send to. Turn on sending, then a target."), 409)
        return {"attempts": [a.to_json() for a in attempts]}

    @app.get("/api/setup/install")
    def install_state() -> Any:
        """What is installed here, and what an install in progress is doing."""
        job = state["installer"].job
        return {"extras": available(), "job": job.to_json() if job else None,
                "running": state["installer"].running()}

    @app.post("/api/setup/install")
    async def install_extra(request: Request) -> Any:
        """
        Install one of DiceCore's optional halves — PyTorch above all.

        The body names a key, and the key picks a constant: handing a user-supplied string
        to pip would be remote code execution wearing a helpful label.
        """
        body = await request.json()
        try:
            job = state["installer"].start(str(body.get("extra", "")))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except RuntimeError as exc:
            return fail(exc, 409)
        return job.to_json()

    @app.post("/api/setup/training/start")
    async def training_start(request: Request) -> Any:
        body = await request.json()
        # One set or several: a model is not tied to one, so a friend's d20s and your own
        # six-siders can go into the same one.
        sets = body.get("set_ids") or ([body["set_id"]] if body.get("set_id") else [])
        try:
            job = training.start([str(s) for s in sets], int(body.get("epochs", 30)),
                                 str(body.get("name", "")))
        except RuntimeError as exc:
            return fail(exc, 409)
        return job.to_json()

    @app.post("/api/setup/training/stop")
    def training_stop() -> Any:
        training.stop()
        return {"ok": True}

    @app.post("/api/setup/training/use")
    async def training_use(request: Request) -> Any:
        """Point the engine at a trained model and switch mode in one step."""
        body = await request.json()
        current = state["settings"]
        current.engine.model_path = str(body.get("path", ""))
        current.engine.mode = "model"
        current.save()
        reader.reload(current)
        try:
            reader.engine()
        except EngineError as exc:
            return fail(exc, 400)
        return {"ok": True, "engine": reader.status()["engine"]}

    # --- the page ---------------------------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    def play_screen() -> Any:
        """
        The game, full screen and without a scrap of admin chrome around it.

        This is the page you put on the television at the table, which is why it is at `/`
        and the setup page is not: the thing you look at all evening should not be one tab
        away behind six you never touch.
        """
        return HTMLResponse((WEB_DIR / "play.html").read_text())

    @app.get("/setup", response_class=HTMLResponse)
    def setup_page() -> Any:
        # Read per request rather than cached: editing the page and hitting reload is how
        # the UI gets developed, and on a Pi the read costs nothing.
        return HTMLResponse((WEB_DIR / "setup.html").read_text())

    @app.get("/play.js")
    def play_script() -> Any:
        return Response((WEB_DIR / "play.js").read_text(), media_type="text/javascript")

    @app.get("/app.js")
    def script() -> Any:
        return Response((WEB_DIR / "app.js").read_text(), media_type="text/javascript")

    @app.get("/style.css")
    def style() -> Any:
        return Response((WEB_DIR / "style.css").read_text(), media_type="text/css")

    @app.get("/play.css")
    def play_style() -> Any:
        return Response((WEB_DIR / "play.css").read_text(), media_type="text/css")

    return app


def _torch_state() -> tuple[bool, str]:
    from ..training.trainer import torch_available

    return torch_available()


def _list_models(settings: Settings) -> list[dict[str, Any]]:
    from ..engine.model import META_FILE, MODEL_FILE

    root = settings.models_dir
    if not root.is_dir():
        return []
    out = []
    for directory in sorted(root.iterdir()):
        if not (directory / MODEL_FILE).is_file():
            continue
        meta: dict[str, Any] = {}
        try:
            meta = json.loads((directory / META_FILE).read_text())
        except (OSError, ValueError):
            pass
        out.append({"path": str(directory), "name": directory.name,
                    "accuracy": meta.get("accuracy"), "samples": meta.get("samples"),
                    "classes": len(meta.get("classes", [])),
                    "trained_at": meta.get("trained_at")})
    return sorted(out, key=lambda m: m.get("trained_at") or 0, reverse=True)
