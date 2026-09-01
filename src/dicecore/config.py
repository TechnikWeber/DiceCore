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
from dataclasses import asdict, dataclass, field, fields
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
class ServerSettings:
    host: str = "0.0.0.0"
    port: int = 8099
    #: Served to the UI so a browser on the LAN can build absolute URLs for consumers.
    public_name: str = "dicecore"


@dataclass
class Settings:
    capture: CaptureSettings = field(default_factory=CaptureSettings)
    tray: TraySettings = field(default_factory=TraySettings)
    engine: EngineSettings = field(default_factory=EngineSettings)
    classic: ClassicSettings = field(default_factory=ClassicSettings)
    settle: SettleSettings = field(default_factory=SettleSettings)
    server: ServerSettings = field(default_factory=ServerSettings)
    #: Keys we did not recognise, kept verbatim so a downgrade is not a data loss.
    extra: dict[str, Any] = field(default_factory=dict)

    # --- paths (derived, never stored) ---
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
        for key, value in (data or {}).items():
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
    """Fill a settings dataclass from a dict, ignoring keys it does not have."""
    names = {f.name for f in fields(prototype)}
    for key, val in value.items():
        if key in names:
            setattr(prototype, key, val)
    return prototype


def config_path() -> Path:
    env = os.environ.get("DICECORE_CONFIG")
    return Path(env) if env else state_dir() / "config.json"
