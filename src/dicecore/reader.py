"""
The thing that actually reads a roll: capture → settle → engine → result.

One object, held by both the CLI and the server, so there is exactly one place where the
camera is open and exactly one place where a mode change takes effect. A dice tower has one
camera; two half-initialised readers fighting over `/dev/video0` is a bug that only shows up
once the UI has more than one tab open.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

from .capture import CaptureError, FrameSource, PushSource, open_source
from .capture.settle import wait_for_settle
from .config import Settings
from .dice import Frame, RollResult
from .engine import Engine, EngineError, build_engine
from .guard import TamperGuard
from .integrity import (
    INFO,
    PENDING,
    VOID,
    WARN,
    Event,
    compare_readings,
    frame_hash,
)
from .modes import ModeSession, interpret
from .modes.catalogue import mode_by_id, rules_for
from .panel import state as phases
from .play import GameSession
from .play import store as game_store


class Reader:
    def __init__(self, settings: Settings,
                 on_phase: Callable[[phases.Presentation], None] | None = None) -> None:
        self.settings = settings
        #: Called on every change worth showing on a screen or a lamp. Set by whoever owns
        #: the outputs; the reader itself neither knows nor cares what is attached.
        self.on_phase = on_phase
        self.push = PushSource()
        self._lock = threading.RLock()
        self._source: FrameSource | None = None
        self._engine: Engine | None = None
        self._last: RollResult | None = None
        self._last_jpeg: bytes | None = None
        self._last_frame: Frame | None = None
        #: Hash of the previous frame's JPEG. Two byte-identical captures cannot happen with
        #: a real sensor, so a repeat means a frozen or replayed feed.
        self._last_frame_hash: str | None = None
        #: Events established while reading, waiting for a hold window to judge them.
        self._pending_events: list[Event] = []
        #: The live game: whose turn it is, how many throws are left, what has been scored.
        #: Owned here because a roll has to reach it before anything is shown — the screen
        #: over the tower says "throw 2 of 3" from the same state the browser does.
        # A game in progress survives a restart: an evening of Kniffel is an hour of
        # somebody's life and a Pi that loses power should not cost it.
        self.game_path = settings.state_dir_path / "game.json"
        restored = game_store.load(self.game_path)
        self.game = restored or GameSession()
        self.game.on_change = lambda session: game_store.save(session, self.game_path)
        if restored is None:
            self.configure_game()
        #: What each game mode remembers between throws — an exploding roll still open, a
        #: fairness tally being built up. One per mode, because two consumers may read the
        #: same tray differently: a screen in "normal" and a bot in "pool" are both right,
        #: and neither should be able to reset the other's tally.
        self.mode_sessions: dict[str, ModeSession] = {}
        #: The hold window runs on its own thread so the number is not held hostage to it.
        self._verifier: threading.Thread | None = None
        self._verify_stop = threading.Event()
        #: Why the source or engine is unavailable, in words the UI can show.
        self.problems: list[str] = []

    # --- lazy, replaceable parts --------------------------------------------
    def source(self) -> FrameSource:
        with self._lock:
            if self._source is None:
                self._source = open_source(self.settings, self.push)
            return self._source

    def engine(self) -> Engine:
        with self._lock:
            if self._engine is None:
                self._engine = build_engine(self.settings)
            return self._engine

    def reload(self, settings: Settings | None = None) -> None:
        """Apply changed settings. Closes the camera, so it is not free — call it on save."""
        self.cancel_verification()
        with self._lock:
            if settings is not None:
                previous = self.settings.mode.active
                self.settings = settings
                self.configure_game()
                if settings.mode.active != previous:
                    # An exploding roll or a fairness tally belongs to the mode that started
                    # it, and to the settings it was collected under. Changing either starts
                    # a fresh one rather than mixing the two.
                    self.mode_sessions.pop(settings.mode.active, None)
            if self._source is not None:
                try:
                    self._source.close()
                except Exception:
                    pass
            self._source = None
            self._engine = None
            self.problems = []

    def close(self) -> None:
        self.cancel_verification()
        with self._lock:
            if self._source is not None:
                self._source.close()
            self._source = None
            self._engine = None

    # --- reading ------------------------------------------------------------
    def read(self, wait_for_still: bool = True, verify: bool | None = None) -> RollResult:
        """
        Read one roll.

        With the guard on, this **blocks for `guard.hold_s` after the reading** while the
        tray is watched — that wait is the feature, not an oversight, and `verify=False`
        turns it off for a caller that only wants the number now.

        Raises `CaptureError` / `EngineError` with a message meant for a human — the UI
        prints them verbatim, because "no camera bound to dtoverlay=imx519" is a repair
        instruction and "read failed" is not.
        """
        # Outside the lock on purpose: the running watch holds it, and this is what makes
        # it let go.
        self.cancel_verification()
        self._emit(phases.waiting(phases.ROLLING if wait_for_still else phases.READING))
        with self._lock:
            source = self.source()
            engine = self.engine()
            settle = self.settings.settle
            guard = self.settings.guard

            warnings: list[str] = []
            threw: bool | None = None
            if wait_for_still and settle.enabled and self.settings.capture.source != "folder":
                outcome = wait_for_settle(source.grab, settle)
                frame = outcome.frame
                if outcome.warning:
                    warnings.append(outcome.warning)
                threw = outcome.peak_motion > settle.motion_threshold
            else:
                frame = source.grab()

            self._emit(phases.waiting(phases.READING))
            result = engine.read(frame)
            result.warnings = warnings + result.warnings
            self.apply_mode(result)
            self._last_frame = frame
            self._last_jpeg = None

            events = self._pre_roll_events(result, frame, threw)
            if result.stale:
                result.warnings.append(
                    "Nothing moved since the last reading and the dice read the same — this "
                    "is the previous roll, not a new throw."
                )

            self._pending_events = events
            self._last = result
            if guard.enabled:
                # Published but not yet judged. A consumer may use the number — `usable` is
                # true — while knowing the verdict has not landed.
                result.verdict = PENDING

            # The game hears about the roll before any screen does, so "throw 2 of 3" and
            # the number arrive together rather than a frame apart.
            self.game.observe(result)
            self._show(result, phases.RESULT)
            if not guard.enabled:
                # Nothing is being watched, so it is already your turn again.
                self._show(result, phases.READY)

            if guard.enabled:
                if verify:
                    self._run_guard(result, frame)
                elif verify is None:
                    # The default: hand the number over now and watch the tray on a thread.
                    # Making every caller wait out the hold window would put two seconds
                    # between the dice landing and anyone seeing a number, which is the
                    # opposite of what a dice tower is for.
                    self._start_verification(result, frame)
            return result

    # --- verification, in the background ------------------------------------
    def _start_verification(self, result: RollResult, frame: Frame) -> None:
        self._verify_stop.clear()
        self._verifier = threading.Thread(
            target=self._verify_quietly, args=(result, frame),
            name="dicecore-guard", daemon=True,
        )
        self._verifier.start()

    def _verify_quietly(self, result: RollResult, frame: Frame) -> None:
        try:
            self._run_guard(result, frame)
        except Exception as exc:
            # A watch that fails must not take the number down with it.
            result.warnings.append(f"Fair play could not finish: {exc}")

    def cancel_verification(self) -> None:
        """
        Stop watching the previous roll, because a new one is starting.

        Throwing again straight away is normal play. Without this the next throw would run
        into the previous roll's hold window, be seen as interference, and void a roll
        nobody was cheating on — and the new read would block behind it.
        """
        if self._verifier is not None and self._verifier.is_alive():
            self._verify_stop.set()
            self._verifier.join(timeout=max(2.0, self.settings.guard.interval_s * 4))
        self._verifier = None

    def verification_running(self) -> bool:
        return self._verifier is not None and self._verifier.is_alive()

    def verify_last(self) -> RollResult:
        """
        Run the hold window over a result that was already handed out.

        This is what lets the event stream answer immediately and correct itself: the number
        goes out as `pending` the moment the dice settle, and the verdict follows once the
        tray has been watched. Calling it twice is a no-op.
        """
        with self._lock:
            result, frame = self._last, self._last_frame
            if result is None or frame is None:
                raise EngineError("Nothing has been read yet, so there is nothing to verify.")
            if result.integrity is None and self.settings.guard.enabled:
                if self.verification_running():
                    # A background watch is already on it; wait for that one rather than
                    # starting a second camera reader.
                    verifier = self._verifier
                    if verifier is not None:
                        self._lock.release()
                        try:
                            verifier.join(timeout=self.settings.guard.hold_s + 2.0)
                        finally:
                            self._lock.acquire()
                    return result
                self._run_guard(result, frame)
            return result

    def _run_guard(self, result: RollResult, frame: Frame) -> None:
        """Watch the tray for `guard.hold_s` and write the verdict onto `result`."""
        source, engine = self.source(), self.engine()
        source.hold(True)
        try:
            integrity = TamperGuard(self.settings.guard).watch(
                grab=source.grab,
                reread=lambda f: engine.read(f).dice,
                sealed=result.dice,
                reference=frame,
                jpeg=self.last_jpeg(),
                prior_events=self._pending_events,
                live=source.is_live,
                should_stop=self._verify_stop.is_set,
            )
        finally:
            source.hold(False)
        result.verdict = integrity.verdict
        result.integrity = integrity.to_json()
        for event in integrity.events:
            if event.severity != INFO and event.detail not in result.warnings:
                result.warnings.append(event.detail)
        # The moment the lamps exist for: the watch is over, throw again.
        self._show(result, phases.VOID if result.verdict == VOID else phases.READY)

    def configure_game(self, force: bool = False) -> None:
        """
        Point the live game at the configured mode, its turn rules and the players.

        Refused while a game is running unless forced. Saving an unrelated setting — a
        buzzer pin, a tray corner — used to reconfigure the session underneath the players,
        and a mode change turned a Kniffel with points on the card into an empty Farkle
        without a word. The lobby starts games; nothing else may take one away.
        """
        if self.game.running and not force:
            return
        mode = mode_by_id(self.settings.mode.active)
        if mode is None:
            return
        params = self.settings.mode.params.get(mode.id) or {}
        rules = rules_for(mode, params)
        self.game.configure(mode.id, rules, list(self.settings.play.players), params=params)
        self.game.colours = list(self.settings.play.colours) or self.game.colours

    def session_for(self, mode_id: str) -> ModeSession:
        session = self.mode_sessions.get(mode_id)
        if session is None:
            session = ModeSession(mode=mode_id)
            self.mode_sessions[mode_id] = session
        return session

    def apply_mode(self, result: RollResult, mode_id: str | None = None) -> RollResult:
        """
        Let the active game mode read the roll.

        Deliberately after the engine and before anything is shown: the engine says what the
        faces are, the mode says what they mean, and everything downstream — screen, lamps,
        API — sees one answer rather than each working it out again.
        """
        mode = self.settings.mode
        active = mode_id or mode.active
        score = interpret(result.dice, active, mode.params.get(active),
                          self.session_for(active), mode.d10_style,
                          mode.d10_zero_counts_as_ten)
        result.reading = {
            "mode": active, "headline": score.headline, "detail": score.detail,
            "value": score.value, "celebrate": score.celebrate, "lament": score.lament,
            "extras": score.extras,
        }
        for warning in score.warnings:
            if warning and warning not in result.warnings:
                result.warnings.append(warning)
        return result

    # --- telling people what is going on -------------------------------------
    def _emit(self, presentation: phases.Presentation) -> None:
        if self.on_phase is not None:
            try:
                self.on_phase(presentation)
            except Exception:
                pass  # a screen must never be able to break a reading

    def _show(self, result: RollResult, phase: str) -> None:
        panel = self.settings.panel
        presentation = phases.presentation_for(result, phase, panel.celebrate,
                                               panel.celebrate_total, panel.lament_on_min,
                                               self.settings.mode.d10_style)
        turn = self.game.turn
        if self.game.rules.multi:
            presentation.turn = {
                "used": turn.rolls_used, "allowed": turn.rolls_allowed,
                "left": turn.rolls_left, "chips": turn.chips_left,
                "player": self.game.players[turn.player % len(self.game.players)],
                "players": len(self.game.players),
            }
        self._emit(presentation)

    def _pre_roll_events(self, result: RollResult, frame: Frame,
                         threw: bool | None) -> list[Event]:
        """
        What is already wrong before the hold window even starts.

        Two things are only visible from here, because they are about the relationship
        between this roll and the previous one rather than about this frame alone.
        """
        events: list[Event] = []
        previous = self._last

        # Only meaningful on a live source: the folder simulator and a push source both
        # hand out the same image again by design.
        jpeg = self.last_jpeg() if self.source().is_live else None
        if jpeg is not None:
            digest = frame_hash(jpeg)
            if digest == self._last_frame_hash:
                events.append(Event(
                    "frozen", WARN,
                    "this capture is byte-identical to the previous one — the video feed is "
                    "frozen or replayed, since a real sensor never repeats exactly",
                ))
            self._last_frame_hash = digest

        if (self.settings.guard.require_throw and threw is False and previous is not None
                and not compare_readings(previous.dice, result.dice)):
            result.stale = True
            events.append(Event("stale", INFO,
                                "the dice did not move since the last reading"))
        return events

    def read_image(self, image: Any, source_name: str = "upload") -> RollResult:
        """Read a frame that came from outside — an upload, or a push from an agent."""
        with self._lock:
            frame = Frame(image=image, source=source_name)
            result = self.apply_mode(self.engine().read(frame))
            self._last = result
            self._last_frame = frame
            self._last_jpeg = None
            return result

    # --- what the UI needs afterwards ---------------------------------------
    @property
    def last(self) -> RollResult | None:
        return self._last

    def last_jpeg(self) -> bytes | None:
        """The frame the last result came from, encoded once and cached."""
        with self._lock:
            if self._last_jpeg is not None:
                return self._last_jpeg
            frame = self._last_frame
            if frame is None:
                return None
            if frame.jpeg:
                self._last_jpeg = frame.jpeg
                return self._last_jpeg
            if frame.image is None:
                return None
            try:
                import cv2
            except ImportError:
                return None
            ok, buf = cv2.imencode(
                ".jpg", frame.image,
                [int(cv2.IMWRITE_JPEG_QUALITY), self.settings.capture.jpeg_quality],
            )
            self._last_jpeg = buf.tobytes() if ok else None
            return self._last_jpeg

    def preview_jpeg(self) -> bytes:
        """A fresh frame for the live view, without running the engine over it."""
        with self._lock:
            frame = self.source().grab()
            self._last_frame = frame
            self._last_jpeg = None
            jpeg = self.last_jpeg()
            if jpeg is None:
                raise CaptureError("Could not encode a preview frame (is OpenCV installed?).")
            return jpeg

    def status(self) -> dict[str, Any]:
        """Everything the overview panel shows, with failures as text rather than as 500s."""
        with self._lock:
            out: dict[str, Any] = {
                "at": time.time(),
                "capture": {"configured": self.settings.capture.source},
                "engine": {"configured": self.settings.engine.mode},
                "problems": [],
            }
            try:
                out["capture"].update(self.source().describe())
            except (CaptureError, Exception) as exc:
                out["problems"].append(str(exc))
            try:
                out["engine"].update(self.engine().describe())
            except (EngineError, Exception) as exc:
                out["problems"].append(str(exc))
            out["last"] = self._last.to_json() if self._last else None
            return out
