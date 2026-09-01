"""
Choosing a CSI camera module from the web UI instead of over SSH.

A Raspberry Pi only sees a camera the firmware knows how to bind. The four official
sensors are found by `camera_auto_detect=1`; everything else — the Arducam modules in
particular — needs `camera_auto_detect=0` plus an explicit `dtoverlay=` in
`/boot/firmware/config.txt` and a reboot.

Ported from YonderRC (`packages/vehicle/src/system/bootConfig.ts`), where these rules were
worked out against real hardware. Everything in here is pure text manipulation so the test
suite can pin down the one file that decides whether the Pi boots at all. The rules are
deliberately conservative: we never rewrite the file, we only comment out the lines that
compete with our choice and append one clearly marked block.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

TUNING_DIR = "/var/lib/dicecore/tuning"

BOOT_CONFIG_PATHS = ("/boot/firmware/config.txt", "/boot/config.txt")


@dataclass(frozen=True)
class CsiModule:
    id: str
    label: str
    #: None means "let the firmware auto-detect".
    overlay: str | None
    #: Shown in the UI so the choice explains itself.
    note: str
    #: Tuning file we ship because the stock one is unusable.
    tuning_file: str | None = None
    #: Module has a focus actuator worth exposing in the camera settings.
    focus: bool = False


CSI_MODULES: tuple[CsiModule, ...] = (
    CsiModule(
        "auto",
        "Auto-detect (official Raspberry Pi cameras)",
        None,
        "Finds OV5647, IMX219, IMX477 and IMX708 (Camera Module 1/2/3 and HQ) on its own.",
    ),
    CsiModule(
        "imx519",
        "Arducam 16MP IMX519 (autofocus)",
        "imx519",
        "Not auto-detected. Needs the shipped tuning file — Raspberry Pi's own imx519.json "
        "has no autofocus algorithm, so the lens never moves and the picture looks soft.",
        tuning_file=f"{TUNING_DIR}/imx519-af.json",
        focus=True,
    ),
    CsiModule("arducam-64mp", "Arducam 64MP Hawkeye (autofocus)", "arducam-64mp",
              "Not auto-detected.", focus=True),
    CsiModule("ov64a40", "Arducam 64MP Owlsight (OV64A40, autofocus)", "ov64a40",
              "Not auto-detected.", focus=True),
    CsiModule("arducam-pivariety", "Arducam Pivariety module", "arducam-pivariety",
              "For Arducam's Pivariety boards, which answer on I²C 0x0c."),
    CsiModule("ov5647", "Raspberry Pi Camera v1 (OV5647), forced", "ov5647",
              "Use when auto-detect misses it."),
    CsiModule("imx219", "Raspberry Pi Camera v2 (IMX219), forced", "imx219",
              "Use when auto-detect misses it."),
    CsiModule("imx477", "Raspberry Pi HQ Camera (IMX477), forced", "imx477",
              "Use when auto-detect misses it."),
    CsiModule("imx708", "Raspberry Pi Camera v3 (IMX708), forced", "imx708",
              "Use when auto-detect misses it.", focus=True),
    CsiModule("custom", "Other module (enter the overlay name)", None,
              "Any overlay shipped in /boot/firmware/overlays. Checked against what is "
              "actually installed before it is written."),
)


def module_by_id(module_id: str) -> CsiModule | None:
    return next((m for m in CSI_MODULES if m.id == module_id), None)


#: Camera overlays we may have to clear when switching modules. Only these are touched — a
#: `dtoverlay=vc4-kms-v3d` or `dwc2` line is none of our business.
CAMERA_OVERLAYS = (
    "imx219", "imx258", "imx283", "imx290", "imx296", "imx327", "imx335", "imx378",
    "imx415", "imx462", "imx477", "imx500", "imx500-pi5", "imx519", "imx708",
    "ov5647", "ov64a40", "ov9281", "arducam-64mp", "arducam-pivariety",
)

BEGIN = "# --- DiceCore camera module (managed by the setup page) ---"
END = "# --- end DiceCore camera module ---"

_AUTO_RE = re.compile(r"^camera_auto_detect\s*=\s*(\d+)")
_DT_RE = re.compile(r"^dtoverlay\s*=\s*(.+)$")
_OVERLAY_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*(,[a-z0-9_-]+(=[A-Za-z0-9_.:-]+)?)*$")


@dataclass(frozen=True)
class BootState:
    #: Raspberry Pi OS defaults to on when the key is absent.
    auto_detect: bool = True
    overlay: str | None = None


def overlay_base_name(value: str) -> str:
    """An overlay may carry parameters (`imx519,vcm`); the catalogue matches on the name."""
    return value.split(",")[0].strip()


def valid_overlay_name(value: str) -> bool:
    """
    A custom overlay name goes into config.txt, so it must not be able to inject a second
    directive. Allow the shape dtoverlay actually uses and nothing else.
    """
    return bool(_OVERLAY_NAME_RE.match(value.strip()))


def parse_boot_config(text: str) -> BootState:
    """Read back what config.txt currently asks for, ignoring commented-out lines."""
    auto_detect = True
    overlay: str | None = None
    for raw in text.split("\n"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        auto = _AUTO_RE.match(line)
        if auto:
            auto_detect = auto.group(1) != "0"
        dt = _DT_RE.match(line)
        if dt and overlay_base_name(dt.group(1)) in CAMERA_OVERLAYS:
            overlay = dt.group(1).strip()
    return BootState(auto_detect, overlay)


def module_id_for(state: BootState) -> str:
    """Which catalogue entry the current config corresponds to."""
    if not state.overlay:
        return "auto" if state.auto_detect else "custom"
    base = overlay_base_name(state.overlay)
    return next((m.id for m in CSI_MODULES if m.overlay == base), "custom")


def strip_managed_block(text: str) -> str:
    """Drop a block we wrote earlier, so applying twice can't stack up."""
    out: list[str] = []
    inside = False
    for line in text.split("\n"):
        if line.strip() == BEGIN:
            inside = True
            continue
        if inside:
            if line.strip() == END:
                inside = False
            continue
        out.append(line)
    return "\n".join(out)


def apply_camera_module(text: str, overlay: str | None) -> str:
    """
    Write the choice into config.txt.

    Competing lines elsewhere in the file are **commented out, not deleted** — the user can
    see what was there and put it back. The new block is appended under its own `[all]` so
    it lands in the unconditional section no matter which `[cm4]`/`[pi5]` section the file
    happened to end in.
    """
    kept: list[str] = []
    for raw in strip_managed_block(text).split("\n"):
        line = raw.strip()
        if not line or line.startswith("#"):
            kept.append(raw)
            continue
        if _AUTO_RE.match(line):
            kept.append(f"# {raw}  # (replaced by DiceCore)")
            continue
        dt = _DT_RE.match(line)
        if dt and overlay_base_name(dt.group(1)) in CAMERA_OVERLAYS:
            kept.append(f"# {raw}  # (replaced by DiceCore)")
            continue
        kept.append(raw)

    block = [BEGIN, "[all]", f"camera_auto_detect={0 if overlay else 1}"]
    if overlay:
        block.append(f"dtoverlay={overlay}")
    block.append(END)
    body = re.sub(r"\n*$", "", "\n".join(kept))
    return f"{body}\n\n" + "\n".join(block) + "\n"


def booted_state_changed(booted: BootState, current: BootState) -> bool:
    """
    A reboot is due when the *effective* configuration differs from what the system booted
    with — comparing file text instead would nag after a change that cancels itself out
    (auto → imx519 → auto rewrites the file but changes nothing the firmware cares about).
    """
    return booted.auto_detect != current.auto_detect or booted.overlay != current.overlay


def explain_boot_config(state: BootState, camera_count: int) -> str | None:
    """What the diagnostics panel should say about the boot config, given what libcamera found."""
    if camera_count > 0:
        return None
    if state.overlay:
        return (
            f"config.txt forces dtoverlay={state.overlay}, but no camera bound to it — wrong "
            "module selected, or the ribbon cable is not seated (contacts towards the HDMI "
            "side, CAM port, not DISPLAY)."
        )
    if state.auto_detect:
        return (
            "camera_auto_detect is on and found nothing. That covers only OV5647 / IMX219 / "
            "IMX477 / IMX708 — pick your module under \"CSI camera module\" if it is an "
            "Arducam or another sensor."
        )
    return (
        "camera_auto_detect is off and no overlay is set, so the firmware never looks for a "
        "camera at all. Pick a module under \"CSI camera module\"."
    )


def known_tuning_files() -> list[str]:
    return [m.tuning_file for m in CSI_MODULES if m.tuning_file]


# --- the one place that touches the real file ------------------------------------


def boot_config_file() -> Path | None:
    return next((Path(p) for p in BOOT_CONFIG_PATHS if Path(p).is_file()), None)


def read_boot_state() -> tuple[BootState, Path | None]:
    path = boot_config_file()
    if path is None:
        return BootState(), None
    try:
        return parse_boot_config(path.read_text(errors="replace")), path
    except OSError:
        return BootState(), path


def write_camera_module(overlay: str | None, path: Path | None = None) -> Path:
    """
    Apply a module to the real config.txt, keeping a one-generation backup beside it.

    Raises `PermissionError` if not run as root — the caller turns that into an
    explanation, because a UI that silently fails to write the boot config is worse than
    one that says "run me as root".
    """
    path = path or boot_config_file()
    if path is None:
        raise FileNotFoundError(
            "No config.txt found — this is not a Raspberry Pi, or /boot is not mounted."
        )
    text = path.read_text(errors="replace")
    backup = path.with_suffix(path.suffix + ".dicecore.bak")
    backup.write_text(text)
    path.write_text(apply_camera_module(text, overlay))
    return path
