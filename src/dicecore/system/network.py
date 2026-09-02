"""
Getting the box onto a network, and opening its own when there is none.

A dice tower lives on a shelf with no keyboard and no screen. If it cannot reach the WiFi —
new house, changed password, moved to a friend's table — there has to be a way in that does
not involve an SSH session, and the answer is the same one YonderRC arrived at: **the box
serves its own network**, a phone joins it, and a captive portal opens the setup page
without anybody typing an address.

Ported from YonderRC (`packages/vehicle/src/system/wifi.ts` and
`transport/captivePortal.ts`), including the parts that were only learned by getting them
wrong on real hardware — see the comments on `hotspot_commands` and `explain_failure`.

Everything that can be decided on strings is a pure function here so the test suite can pin
it down; the shell calls are a thin layer at the bottom and fail politely off a Pi.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any

#: The connection profile we create. Named so it is obvious in `nmcli con show`.
HOTSPOT_CON_NAME = "dicecore-setup"
#: The address the box gives itself on its own network. 10.x to stay out of the way of the
#: 192.168.x a home router almost certainly uses.
HOTSPOT_ADDRESS = "10.42.0.1"
WIFI_IFACE = "wlan0"

#: NetworkManager's dnsmasq drop-in, read for *shared* connections only.
CAPTIVE_CONF_PATH = "/etc/NetworkManager/dnsmasq-shared.d/dicecore-captive.conf"

_COUNTRY = re.compile(r"^[A-Za-z]{2}$")


# --- reading what the system says -------------------------------------------------


@dataclass
class RadioState:
    """What the WiFi radio is doing, and whether it can do anything at all."""

    soft_blocked: bool = False
    hard_blocked: bool = False
    country: str | None = None

    @property
    def usable(self) -> bool:
        return not self.soft_blocked and not self.hard_blocked and bool(self.country)

    def to_json(self) -> dict[str, Any]:
        return {"soft_blocked": self.soft_blocked, "hard_blocked": self.hard_blocked,
                "country": self.country, "usable": self.usable}


def parse_rfkill(out: str) -> tuple[bool, bool]:
    """`rfkill list wifi` → (soft blocked, hard blocked)."""
    soft = hard = False
    for line in out.splitlines():
        low = line.lower().strip()
        if low.startswith("soft blocked:"):
            soft = soft or low.endswith("yes")
        elif low.startswith("hard blocked:"):
            hard = hard or low.endswith("yes")
    return soft, hard


def parse_wifi_country(out: str) -> str | None:
    """`iw reg get` or `raspi-config nonint get_wifi_country` → a country code."""
    match = re.search(r"country\s+([A-Z]{2})", out) or re.match(r"^\s*([A-Za-z]{2})\s*$", out)
    if not match:
        return None
    code = match.group(1).upper()
    return None if code == "00" else code


def is_country_code(value: Any) -> bool:
    return isinstance(value, str) and bool(_COUNTRY.match(value.strip()))


def parse_device_state(out: str, iface: str = WIFI_IFACE) -> str:
    """
    `nmcli -t -f DEVICE,STATE device` → this interface's state word.

    "unavailable" is the one that matters: it is nmcli's way of saying the radio is blocked,
    which on a Pi almost always means no WiFi country has ever been set.
    """
    for line in out.splitlines():
        parts = line.split(":")
        if len(parts) >= 2 and parts[0] == iface:
            return parts[1]
    return "missing"


def parse_mode(out: str, iface: str = WIFI_IFACE) -> str:
    """`iw dev <iface> info` → client | ap | unknown. Serving and joining look alike."""
    if re.search(r"type\s+AP", out):
        return "ap"
    if re.search(r"type\s+managed", out):
        return "client"
    return "unknown"


def parse_networks(out: str) -> list[dict[str, Any]]:
    """
    `nmcli -t -f SSID,SIGNAL,SECURITY device wifi list` → what is in range.

    Deduplicated by name and sorted by signal, because a mesh shows the same SSID four times
    and a list of four identical rows helps nobody choose.
    """
    best: dict[str, dict[str, Any]] = {}
    for line in out.splitlines():
        parts = line.split(":")
        if len(parts) < 3 or not parts[0].strip():
            continue
        ssid = parts[0]
        try:
            signal = int(parts[1] or 0)
        except ValueError:
            signal = 0
        entry = {"ssid": ssid, "signal": signal,
                 "security": (parts[2] or "").strip() or "open"}
        if ssid not in best or signal > best[ssid]["signal"]:
            best[ssid] = entry
    return sorted(best.values(), key=lambda n: -n["signal"])


def parse_active(out: str) -> dict[str, Any]:
    """`nmcli -t -f NAME,DEVICE,TYPE,STATE connection show --active` → what is connected."""
    connections = []
    for line in out.splitlines():
        parts = line.split(":")
        if len(parts) >= 4:
            connections.append({"name": parts[0], "device": parts[1],
                                "type": parts[2], "state": parts[3]})
    return {"connections": connections,
            "ethernet": any(c["type"].endswith("ethernet") for c in connections),
            "wifi": any(c["type"].endswith("wireless") for c in connections),
            "hotspot": any(c["name"] == HOTSPOT_CON_NAME for c in connections)}


# --- building the commands --------------------------------------------------------


@dataclass
class HotspotProfile:
    ssid: str = "DiceCore-setup"
    #: Blank or under eight characters means an open network — which is usually what you
    #: want for a box you are trying to reach *because* you cannot reach it.
    password: str = ""

    @property
    def secured(self) -> bool:
        return len(self.password or "") >= 8


def hotspot_commands(profile: HotspotProfile, iface: str = WIFI_IFACE) -> list[list[str]]:
    """
    The nmcli invocations that (re)create and start the onboarding hotspot, in order.

    Built explicitly rather than with `nmcli device wifi hotspot`, for two reasons learned
    the hard way in YonderRC: that command cannot produce an **open** network, and it picks
    its own address. An open network is the point — somebody who cannot reach the box also
    cannot be told a password.

    Each entry is an argv list, never a shell string, so an SSID containing spaces, quotes
    or semicolons is simply text.
    """
    ssid = (profile.ssid or "DiceCore-setup").strip() or "DiceCore-setup"
    commands: list[list[str]] = [
        # A stale profile from an earlier run would keep its old SSID and security.
        ["connection", "delete", HOTSPOT_CON_NAME],
        ["connection", "add", "type", "wifi", "ifname", iface,
         "con-name", HOTSPOT_CON_NAME, "autoconnect", "no", "ssid", ssid,
         "802-11-wireless.mode", "ap", "802-11-wireless.band", "bg",
         "ipv4.method", "shared", "ipv4.addresses", f"{HOTSPOT_ADDRESS}/24"],
    ]
    if profile.secured:
        commands.append(["connection", "modify", HOTSPOT_CON_NAME,
                         "wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.psk", profile.password,
                         "wifi-sec.proto", "rsn", "wifi-sec.pairwise", "ccmp",
                         "wifi-sec.group", "ccmp"])
    commands.append(["connection", "up", HOTSPOT_CON_NAME])
    return commands


def join_commands(ssid: str, password: str, iface: str = WIFI_IFACE) -> list[list[str]]:
    """Join a network. The hotspot is taken down first — one radio cannot do both."""
    commands = [["connection", "down", HOTSPOT_CON_NAME]]
    join = ["device", "wifi", "connect", ssid, "ifname", iface]
    if password:
        join += ["password", password]
    commands.append(join)
    return commands


def wifi_country_args(code: str) -> list[str]:
    """`raspi-config nonint do_wifi_country DE`. The code is validated before it gets here."""
    return ["nonint", "do_wifi_country", code.strip().upper()]


def captive_portal_conf(address: str = HOTSPOT_ADDRESS) -> str:
    """Resolve every name to the box — this is what makes a phone show the portal."""
    return f"address=/#/{address}\n"


def should_hijack_dns(has_uplink: bool) -> bool:
    """
    Hijack DNS only when the box has no uplink of its own.

    With an uplink the hotspot shares real internet, and pointing every name at the Pi would
    break the internet for everyone connected — while the portal it triggers is pointless,
    because those clients are already online. Without an uplink it is the whole trick that
    opens the page unprompted.
    """
    return not has_uplink


@dataclass
class Failure:
    cause: str
    fix: str
    #: True when the setup page itself can repair this, rather than only explain it.
    fixable_here: bool = False

    def to_json(self) -> dict[str, Any]:
        return {"cause": self.cause, "fix": self.fix, "fixable_here": self.fixable_here}


def explain_failure(out: str, radio: RadioState | None = None) -> Failure:
    """
    Turn an nmcli failure into something somebody can act on.

    "Device is not available" is nmcli's way of saying rfkill has the radio blocked because
    no WiFi country was ever set — a sentence nobody guesses from the message itself, and
    the single most common reason a fresh Pi's hotspot never appears.
    """
    low = (out or "").lower()
    if radio and radio.hard_blocked:
        return Failure("The WiFi radio is blocked by a hardware switch.",
                       "Some boards have a physical switch or a BIOS setting for it.")
    if radio and radio.soft_blocked and not radio.country:
        return Failure(
            "The WiFi radio is blocked because no country has been set.",
            "Pick a country below — a Pi refuses to transmit until it knows which rules "
            "apply. This is almost always why a fresh Pi's hotspot never appears.",
            fixable_here=True)
    if radio and radio.soft_blocked:
        return Failure("The WiFi radio is soft-blocked.",
                       "Unblock it below (`rfkill unblock wifi`).", fixable_here=True)
    if "not available" in low or "unavailable" in low:
        return Failure(
            "NetworkManager says the WiFi device is not available.",
            "Usually the radio is blocked and no country is set — try setting one below.",
            fixable_here=True)
    if "secrets were required" in low or "no key available" in low or "802.1x" in low:
        return Failure("The password was refused.", "Check it and try again.")
    if "no network with ssid" in low or "not found" in low:
        return Failure("That network was not in range when the box looked.",
                       "Scan again, or move the box closer.")
    if "not authorized" in low or "permission" in low:
        return Failure("Not allowed to change the network.",
                       "DiceCore has to run as root or with a polkit rule to manage WiFi.")
    return Failure(out.strip().splitlines()[-1] if out.strip() else "Unknown failure.",
                   "See `journalctl -u NetworkManager` for what NetworkManager made of it.")


# --- the thin layer that actually runs things -------------------------------------


def _run(argv: list[str], timeout: float = 25.0) -> tuple[int, str]:
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                              env={"LC_ALL": "C", "PATH": "/usr/sbin:/usr/bin:/sbin:/bin"})
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, str(exc)


@dataclass
class Network:
    """
    The box's network, as far as it can be managed from here.

    Every method answers rather than raises: a box that cannot reach the network is exactly
    the box whose setup page has to keep working.
    """

    iface: str = WIFI_IFACE
    #: Last failure, kept so the page can show it after a redirect.
    last_error: Failure | None = None
    _cache: dict[str, Any] = field(default_factory=dict)

    @property
    def available(self) -> bool:
        return shutil.which("nmcli") is not None

    def radio(self) -> RadioState:
        if not shutil.which("rfkill"):
            return RadioState(country=None)
        soft, hard = parse_rfkill(_run(["rfkill", "list", "wifi"])[1])
        country = None
        if shutil.which("iw"):
            country = parse_wifi_country(_run(["iw", "reg", "get"])[1])
        return RadioState(soft, hard, country)

    def status(self) -> dict[str, Any]:
        """Everything the network panel shows. Never raises, never blocks for long."""
        if not self.available:
            return {"managed": False, "reason": (
                "NetworkManager is not installed here, so DiceCore cannot manage the "
                "network. On Raspberry Pi OS Bookworm it is there by default; elsewhere "
                "this panel is read-only."), "radio": self.radio().to_json()}
        active = parse_active(_run(["nmcli", "-t", "-f", "NAME,DEVICE,TYPE,STATE",
                                    "connection", "show", "--active"])[1])
        device = parse_device_state(_run(["nmcli", "-t", "-f", "DEVICE,STATE", "device"])[1],
                                    self.iface)
        mode = parse_mode(_run(["iw", "dev", self.iface, "info"])[1], self.iface) \
            if shutil.which("iw") else "unknown"
        return {
            "managed": True,
            "radio": self.radio().to_json(),
            "device": device,
            "mode": mode,
            "hotspot": active["hotspot"],
            "ethernet": active["ethernet"],
            "wifi": active["wifi"] and not active["hotspot"],
            "online": self.has_uplink(),
            "connections": active["connections"],
            "address": self.address(),
            "error": self.last_error.to_json() if self.last_error else None,
        }

    def address(self) -> str | None:
        code, out = _run(["hostname", "-I"], timeout=5)
        return out.split()[0] if code == 0 and out.split() else None

    def has_uplink(self) -> bool:
        """Any default route at all — the question the DNS hijack turns on."""
        code, out = _run(["ip", "route", "show", "default"], timeout=5)
        return code == 0 and "default" in out

    def scan(self) -> list[dict[str, Any]]:
        if not self.available:
            return []
        _run(["nmcli", "device", "wifi", "rescan"], timeout=20)
        return parse_networks(_run(
            ["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list"])[1])

    def set_country(self, code: str) -> tuple[bool, str]:
        if not is_country_code(code):
            return False, f"{code!r} is not a two-letter country code."
        if shutil.which("raspi-config"):
            status, out = _run(["raspi-config", *wifi_country_args(code)])
            if status != 0:
                return False, out.strip()[:200]
        _run(["rfkill", "unblock", "wifi"])
        return True, f"WiFi country set to {code.upper()}. The radio should come up now."

    def unblock(self) -> tuple[bool, str]:
        status, out = _run(["rfkill", "unblock", "wifi"])
        return status == 0, out.strip()[:200] or "Radio unblocked."

    def join(self, ssid: str, password: str = "") -> tuple[bool, str]:
        """
        Join a network. One radio, so the hotspot goes down first and comes back on failure.

        Coming back matters more than it sounds: a wrong password with no hotspot afterwards
        leaves a box on a shelf with no way in at all.
        """
        if not self.available:
            return False, "NetworkManager is not installed here."
        if not ssid:
            return False, "No network name."
        for argv in join_commands(ssid, password, self.iface):
            status, out = _run(["nmcli", *argv], timeout=45)
            if status != 0 and argv[:2] != ["connection", "down"]:
                self.last_error = explain_failure(out, self.radio())
                self.start_hotspot(self._cache.get("profile") or HotspotProfile())
                return False, self.last_error.cause
        self.last_error = None
        return True, f'Connected to "{ssid}". The hotspot is closing; rejoin your own WiFi.'

    def start_hotspot(self, profile: HotspotProfile | None = None) -> tuple[bool, str]:
        profile = profile or HotspotProfile()
        self._cache["profile"] = profile
        if not self.available:
            return False, "NetworkManager is not installed here."
        radio = self.radio()
        if not radio.usable:
            self.last_error = explain_failure("", radio)
            return False, self.last_error.cause
        for argv in hotspot_commands(profile, self.iface):
            status, out = _run(["nmcli", *argv], timeout=45)
            if status != 0 and argv[:2] != ["connection", "delete"]:
                self.last_error = explain_failure(out, radio)
                return False, self.last_error.cause
        self.write_captive_conf()
        self.last_error = None
        password = f' with the password "{profile.password}"' if profile.secured else " (open)"
        return True, f'Serving "{profile.ssid}"{password}. Join it and the page should open.'

    def stop_hotspot(self) -> tuple[bool, str]:
        status, out = _run(["nmcli", "connection", "down", HOTSPOT_CON_NAME])
        return status == 0, "Hotspot stopped." if status == 0 else out.strip()[:200]

    def write_captive_conf(self) -> bool:
        """
        Point every name at the box — but only while it has no uplink of its own.

        With an uplink the hotspot shares real internet, and hijacking DNS would break it
        for everybody on it while triggering a portal they do not need.
        """
        from pathlib import Path

        path = Path(CAPTIVE_CONF_PATH)
        try:
            if should_hijack_dns(self.has_uplink()):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(captive_portal_conf())
            else:
                path.unlink(missing_ok=True)
            return True
        except OSError:
            # Needs root. The hotspot still works; the page just has to be typed in.
            return False
