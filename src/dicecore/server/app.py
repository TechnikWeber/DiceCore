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
import json
import time
from pathlib import Path
from typing import Any

from ..capture import SOURCES, CaptureError
from ..config import Settings, config_path
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
    state: dict[str, Any] = {"settings": loaded, "complaints": complaints, "hub": None}
    hub = OutputHub(loaded.panel)
    state["hub"] = hub
    reader = Reader(loaded, on_phase=lambda p: state["hub"].update(p))
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

    app = FastAPI(title="DiceCore", version="0.10.0",
                  description="Reads real dice with a camera.")
    app.state.reader = reader
    app.state.training = training
    app.state.hub = hub
    app.state.buttons = buttons
    installer = Installer()
    state["installer"] = installer

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
                "buttons": state["buttons"].describe()}

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

    @app.websocket("/api/v1/events")
    async def events(socket: WebSocket) -> None:
        """
        Push every new result as it happens.

        Polling `/roll` would capture on every poll; this reads on its own schedule and
        emits only when the result actually changes, which is what a bot wants.
        """
        await socket.accept()
        previous: str | None = None
        try:
            while True:
                if not reader.game.running:
                    # Nothing is being played, so nothing is looked at. This is what makes
                    # the lobby honest — and it is also why the Pi is not capturing all
                    # night for an empty table.
                    await socket.send_text(json.dumps({"idle": True,
                                                       "game": reader.game.to_json()}))
                    await asyncio.sleep(1.0)
                    previous = None
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
                    payload = json.dumps(body, sort_keys=True)
                    if payload != previous:
                        previous = payload
                        await socket.send_text(payload)
                        if state["settings"].guard.enabled:
                            verified = await asyncio.to_thread(reader.verify_last)
                            after = verified.to_json()
                            after["game"] = reader.game.to_json()
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
        return {"ok": True, "settings": updated.to_dict()}

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
        try:
            job = training.start(str(body.get("set_id", "")), int(body.get("epochs", 30)),
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
