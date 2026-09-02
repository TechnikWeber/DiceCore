"""
Settings: one JSON file, one dataclass tree, no dependencies.

Every knob the web UI offers lives here. Two rules that the rest of the code relies on:

* **Unknown keys survive a round trip.** A config written by a newer version must not be
  destroyed by an older one, and a half-finished feature must not lose the user's value.
* **Loading never throws on bad content.** A Pi that cannot parse its config still has to
  come up far enough to be fixed through the UI, so a broken file degrades to defaults
  plus a loud warning instead of a dead service.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any


def state_dir() -> Path:
    """Where frames, datasets, models and the config live."""
    env = os.environ.get("DICECORE_STATE")
    if env:
        return Path(env)
    system = Path("/var/lib/dicecore")
    if system.is_dir() and os.access(system, os.W_OK):
        return system
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "dicecore"


@dataclass
class CaptureSettings:
    #: folder (simulator) | v4l2 | rpicam | picamera2 | push
    source: str = "folder"
    #: `folder`: directory of images played back in order. `v4l2`: /dev/videoN index.
    folder: str = ""
    device: int = 0
    width: int = 1280
    height: int = 720
    rotation: int = 0
    jpeg_quality: int = 85
    #: CSI module id from system.boot_config.CSI_MODULES ("auto", "imx519", …).
    csi_module: str = "auto"
    #: libcamera tuning file. The Arducam IMX519 needs the shipped one or its lens never
    #: moves — Raspberry Pi's own imx519.json has no autofocus algorithm at all.
    tuning_file: str = ""
    #: manual | auto | continuous — only meaningful on a module with a focus actuator.
    focus_mode: str = "manual"
    focus_dioptre: float = 0.0


@dataclass
class TraySettings:
    """
    The landing area. Everything outside it is ignored, which removes most false positives
    (table edges, hands, the tower itself) before any recognition happens.
    """

    #: Fractions of the frame (0..1) so the ROI survives a resolution change.
    x: float = 0.0
    y: float = 0.0
    w: float = 1.0
    h: float = 1.0
    #: Millimetres per pixel inside the tray, measured once. Turns "this blob is 40px" into
    #: "this blob is 16mm", which is how a d6 is told apart from a d20 by size alone.
    mm_per_px: float = 0.0


@dataclass
class EngineSettings:
    #: classic | model | remote | auto (model if one is loaded, else classic)
    mode: str = "auto"
    model_path: str = ""
    #: For mode=remote: base URL of another DiceCore instance, e.g. http://desk.local:8099
    remote_url: str = ""
    remote_timeout_s: float = 5.0
    #: Which kinds may appear. Narrowing this is the cheapest accuracy win there is.
    expected_kinds: list[str] = field(default_factory=lambda: ["d6"])
    #: Below this the result is reported but flagged, and the UI asks you to confirm.
    min_confidence: float = 0.6


@dataclass
class ClassicSettings:
    """Knobs of the no-training engine. Exposed because tray and lighting vary per setup."""

    #: Dice are lighter than the tray by default; flip for white trays.
    dice_are_light: bool = True
    #: Plausible die footprint as a fraction of the tray area. Rejects crumbs and shadows.
    min_area_frac: float = 0.0015
    max_area_frac: float = 0.08
    #: How square a die outline has to be (w/h ratio bounds).
    min_aspect: float = 0.6
    max_aspect: float = 1.7
    #: Blur radius before thresholding, in pixels; 0 disables.
    blur: int = 5
    #: A pip must cover at least this fraction of the die's own area.
    min_pip_area_frac: float = 0.005
    max_pip_area_frac: float = 0.12
    #: Pips darker than the face — white dice with black pips, the usual case. Turn it off
    #: for black or dark coloured dice with light pips, which the counter otherwise cannot
    #: see at all: it looks for dark blobs and there are none.
    pips_are_dark: bool = True
    #: Name each die's colour as well as its face. Off by default — it costs a little work
    #: per die and most games do not care. Turn it on for the games that are *about* the
    #: colours, or to tell one player's dice from another's on a shared tray.
    detect_colour: bool = False


@dataclass
class SettleSettings:
    """A frame grabbed mid-tumble is worthless, so a roll is only read once it stops."""

    enabled: bool = True
    #: Mean absolute frame difference (0..255) below which the scene counts as still.
    motion_threshold: float = 2.0
    #: Consecutive still frames required before reading.
    stable_frames: int = 3
    #: Give up waiting after this long and read whatever is there, flagged.
    timeout_s: float = 6.0


@dataclass
class GuardSettings:
    """
    Fair play. What happens to the tray *after* the number was read.

    Defaults are deliberately mild: watch, report, do not withhold. A game night where a
    legitimate roll gets thrown away because someone reached past the tower for their drink
    is worse than one where a suspicious roll is merely marked as suspicious.
    """

    enabled: bool = True
    #: off | flag (report and mark) | void (a disturbed roll is discarded)
    policy: str = "flag"
    #: How long the tray stays under watch after the reading, in seconds.
    hold_s: float = 2.0
    #: How often to look during the hold.
    interval_s: float = 0.15
    #: Mean frame difference (0..255) that counts as something happening.
    motion_threshold: float = 2.0
    #: A change region this large a fraction of the frame reads as a hand, not a die.
    hand_area_frac: float = 0.05
    #: Byte-identical frames in a row that mean the feed is frozen rather than the dice.
    #: A real sensor always has noise, so this cannot happen by accident.
    freeze_frames: int = 6
    #: Brightness below this fraction of the reading frame's means the lens was covered.
    dark_fraction: float = 0.35
    #: How far a die may drift (as a fraction of its own size) before it counts as moved.
    move_tolerance: float = 0.4
    #: Under policy=void, void even when the dice read the same after a hand reached in.
    void_on_touch: bool = False
    #: Read the tray a second time even when nothing was seen. Cheap insurance against a
    #: change that happened entirely between two frames.
    always_recheck: bool = True
    #: Refuse to report a reading that was never preceded by an actual throw — this is what
    #: stops the same lucky roll being reported twice.
    require_throw: bool = True


@dataclass
class ModeSettings:
    """
    Which game is being played, which decides how the faces are read.

    DiceCore reads dice; a mode reads the *result*. Keeping the two apart is what stops the
    project being about one game — see `modes/catalogue.py` for the list and
    `docs/GAME-MODES.md` for what each one does.
    """

    #: Id from modes.catalogue. "normal" is plain six-siders added up.
    active: str = "normal"
    #: How this set's ten-sided dice are printed: "0-9" or "1-10". A property of the dice
    #: themselves — it decides the labels a model is trained on.
    d10_style: str = "0-9"
    #: What a zero on a 0–9 die is worth. Ten in nearly every game, which is why that is the
    #: default — but some house rules count it as nothing, and then a 0 really is a 0. A mode
    #: may still override it; this is the answer for everything that does not.
    d10_zero_counts_as_ten: bool = True
    #: Per-mode parameter overrides, keyed by mode id: {"pool": {"threshold": 5}}.
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class DisplaySettings:
    """
    A small screen over the tower, so the number is public the moment it is read.

    Which matters more than it looks: a number everyone can see the instant the dice stop
    cannot be quietly changed afterwards, because everybody already read it.
    """

    enabled: bool = False
    #: preview | st7789 | ili9341 | ssd1306 | ssd1306-spi — see output/displays.py
    kind: str = "preview"
    #: 0 uses the panel's own default (240x240 for ST7789, 320x240 for ILI9341, 128x64 OLED).
    width: int = 0
    height: int = 0
    #: Quarter turns, 0-3, for a panel mounted sideways.
    rotate: int = 0
    spi_port: int = 0
    spi_device: int = 0
    #: BCM numbers. These are the pins nearly every breakout board's guide uses.
    gpio_dc: int = 25
    gpio_rst: int = 24
    i2c_port: int = 1
    #: Hex string, because that is how every OLED's documentation writes it.
    i2c_address: str = "0x3C"
    contrast: int = 255


@dataclass
class SignalSettings:
    """
    Two lamps and a buzzer: the answer to "is it my turn yet" without looking at a screen.

    Green means throw. Red means the tray is being read or watched — hands off. The buzzer
    marks the two moments worth hearing: the number is in, and you may throw again.
    """

    enabled: bool = False
    #: BCM pin numbers. -1 disables that one signal without disabling the rest.
    green_pin: int = 17
    red_pin: int = 27
    buzzer_pin: int = 22
    buzzer_enabled: bool = True
    #: False for the common transistor/relay boards that pull the pin low to switch on.
    active_high: bool = True
    beep_ms: int = 70
    #: A natural 20 gets a small flourish; a natural 1 gets a low one. Set false for a
    #: table that has decided the beeping is enough.
    celebrate_sound: bool = True

    # --- buttons: the panel listens as well as speaks ---------------------
    #: Spend a chip — one extra throw in a game that allows them. -1 for no button.
    chip_pin: int = -1
    #: End the turn / book nothing / hand the tower on.
    next_pin: int = -1
    #: True for a button wired to ground (the usual case, using the Pi's own pull-up).
    button_pull_up: bool = True
    #: Ignore repeats within this long, so one press is one press.
    debounce_s: float = 0.08


@dataclass
class PanelSettings:
    """The screen, the lamps, the buttons, and what counts as a roll worth celebrating."""

    display: DisplaySettings = field(default_factory=DisplaySettings)
    signals: SignalSettings = field(default_factory=SignalSettings)
    #: off | max_die (a natural maximum on any die) | near_max (the sum reaches a fraction
    #: of the best these dice could show) | total (an absolute threshold)
    celebrate: str = "max_die"
    celebrate_total: int = 18
    #: A natural 1 gets its own, quieter acknowledgement.
    lament_on_min: bool = True
    #: Frames in the celebration animation, and how fast they run.
    animation_frames: int = 12
    animation_interval_s: float = 0.06


@dataclass
class PlaySettings:
    """The game screen at the table."""

    #: Who is playing. Two by default, because that is the common case and because the
    #: game screen should be usable without typing anything at all.
    players: list[str] = field(default_factory=lambda: ["Player 1", "Player 2"])
    #: One colour per player, assigned automatically and changeable by tapping.
    colours: list[str] = field(default_factory=list)


@dataclass
class PublishSettings:
    """
    Sending finished rolls somewhere else — Discord, Avrae, or any URL.

    All off by default. Handing a number to a third party is a thing a table decides, and
    two of these carry a credential.
    """

    enabled: bool = False
    #: Skip rolls the fair-play watch voided. On by default: a number that was interfered
    #: with is exactly the one you do not want turning up in a game.
    only_usable: bool = True

    # --- Avrae: write the roll into a user variable an alias can read ------
    avrae_enabled: bool = False
    #: From avrae.io/dashboard. A credential: it can read and write that account's aliases
    #: and variables, and it sits in this config file in plain text.
    avrae_token: str = ""
    #: The variable name the Discord alias reads with get_uvar().
    avrae_uvar: str = "dicecore"
    #: Blank means the official API. Set it only if you run your own Avrae.
    avrae_api: str = ""

    # --- Discord: a message in a channel ----------------------------------
    discord_enabled: bool = False
    #: Channel settings → Integrations → Webhooks → New webhook → Copy URL.
    discord_webhook: str = ""
    discord_name: str = "DiceCore"

    # --- anything else ----------------------------------------------------
    webhook_enabled: bool = False
    #: Gets the same JSON the API returns for a roll, POSTed as it happens.
    webhook_url: str = ""


@dataclass
class ServerSettings:
    host: str = "0.0.0.0"
    port: int = 8099
    #: Served to the UI so a browser on the LAN can build absolute URLs for consumers.
    public_name: str = "dicecore"
    #: Offer a live view of the tray at /api/v1/stream.mjpg — for playing with people who
    #: are not in the room and would like to see the dice land.
    #:
    #: **Off by default, on purpose.** The still preview the setup page already uses is one
    #: picture when somebody asks for it; a continuous stream of whatever the camera can see
    #: is a different thing to leave running on an unauthenticated port, and that is a
    #: decision for whoever owns the room rather than a default.
    stream_enabled: bool = False
    #: Frames a second for that stream. Low on purpose: it shares the camera with the
    #: reading, and a dice tray is not sport.
    stream_fps: int = 5


@dataclass
class Settings:
    capture: CaptureSettings = field(default_factory=CaptureSettings)
    tray: TraySettings = field(default_factory=TraySettings)
    engine: EngineSettings = field(default_factory=EngineSettings)
    classic: ClassicSettings = field(default_factory=ClassicSettings)
    settle: SettleSettings = field(default_factory=SettleSettings)
    guard: GuardSettings = field(default_factory=GuardSettings)
    mode: ModeSettings = field(default_factory=ModeSettings)
    play: PlaySettings = field(default_factory=PlaySettings)
    panel: PanelSettings = field(default_factory=PanelSettings)
    publish: PublishSettings = field(default_factory=PublishSettings)
    server: ServerSettings = field(default_factory=ServerSettings)
    #: Keys we did not recognise, kept verbatim so a downgrade is not a data loss.
    extra: dict[str, Any] = field(default_factory=dict)

    # --- paths (derived, never stored) ---
    @property
    def state_dir_path(self) -> Path:
        return state_dir()

    @property
    def dataset_dir(self) -> Path:
        return state_dir() / "datasets"

    @property
    def models_dir(self) -> Path:
        return state_dir() / "models"

    @property
    def frames_dir(self) -> Path:
        return state_dir() / "frames"

    # --- (de)serialisation ---
    def to_dict(self) -> dict[str, Any]:
        out = {f.name: asdict(getattr(self, f.name)) for f in fields(self) if f.name != "extra"}
        out.update(self.extra)
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Settings:
        known = {f.name: f for f in fields(cls) if f.name != "extra"}
        kwargs: dict[str, Any] = {}
        extra: dict[str, Any] = {}
        data = dict(data or {})
        # The screen and lamps section was called "output" before the buttons arrived and
        # made it a panel rather than an output. Carry an old config over instead of
        # silently handing someone back the defaults.
        if "output" in data and "panel" not in data:
            data["panel"] = data.pop("output")
        for key, value in data.items():
            spec = known.get(key)
            if spec is None or not isinstance(value, dict):
                extra[key] = value
                continue
            # `spec.type` is a string here (PEP 563), so build a fresh default and fill it.
            kwargs[key] = _build(spec.default_factory(), value)
        return cls(extra=extra, **kwargs)

    def save(self, path: Path | None = None) -> Path:
        path = path or config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write-then-rename: a power cut during a save must not leave an empty config on a
        # box whose only repair channel is the web UI that config starts.
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n")
        tmp.replace(path)
        return path

    @classmethod
    def load(cls, path: Path | None = None) -> tuple[Settings, list[str]]:
        """Returns the settings and any complaints worth showing in the UI."""
        path = path or config_path()
        if not path.exists():
            return cls(), []
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError) as exc:
            return cls(), [f"{path} is unreadable ({exc}) — running on defaults."]
        if not isinstance(data, dict):
            return cls(), [f"{path} does not contain an object — running on defaults."]
        return cls.from_dict(data), []


def _build(prototype: Any, value: dict[str, Any]) -> Any:
    """
    Fill a settings dataclass from a dict, ignoring keys it does not have.

    Recurses, because settings nest: `output.display.kind` is two levels down, and a
    non-recursive version quietly left it as a plain dict — which then failed much later,
    at the point where something tried to use it as a settings object.
    """
    names = {f.name: f for f in fields(prototype)}
    for key, val in value.items():
        field_spec = names.get(key)
        if field_spec is None:
            continue
        current = getattr(prototype, key, None)
        if is_dataclass(current) and isinstance(val, dict):
            setattr(prototype, key, _build(current, val))
        else:
            setattr(prototype, key, val)
    return prototype


def config_path() -> Path:
    env = os.environ.get("DICECORE_CONFIG")
    return Path(env) if env else state_dir() / "config.json"
