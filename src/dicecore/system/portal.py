"""
The captive portal, and the decision to open the box's own network at all.

A dice tower sits on a shelf with no keyboard and no screen. When it cannot reach the WiFi —
a new house, a changed password, somebody else's table — the way in has to be something a
person can do with a phone. So: the box serves its own network, and a tiny server on port 80
answers the "am I online?" probes every phone makes in a way that makes it pop the setup page
open by itself.

Two small servers rather than one, because they answer different questions. Port 80 exists
only to say "not the internet, go here"; the real page stays where it always was.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

#: How long the box must be without a network before it opens its own. Long enough not to
#: react to a router rebooting, short enough that somebody standing there does not give up.
DEFAULT_GRACE_S = 45.0
#: How often to look.
CHECK_EVERY_S = 15.0


def portal_target(host: str, control_port: int) -> str:
    """Where a probe is sent. The host is whatever the phone asked for, minus any port."""
    return f"http://{host.split(':')[0]}:{control_port}/setup"


class _Handler(BaseHTTPRequestHandler):
    control_port = 8099

    def do_GET(self) -> None:  # noqa: N802 - http.server's naming
        # Apple expects exactly "Success" when online and anything else triggers the captive
        # UI; Android and Windows work the same way. So: redirect everything, always.
        target = portal_target(self.headers.get("Host", ""), self.control_port)
        self.send_response(302)
        self.send_header("Location", target)
        self.send_header("Content-Length", "0")
        self.end_headers()

    do_POST = do_GET

    def log_message(self, *args: Any) -> None:
        """Silence. A captive portal is hit by every probe on the network, constantly."""


class CaptivePortal:
    """The port-80 redirector. Needs root; off a Pi it simply does not start."""

    def __init__(self, control_port: int = 8099) -> None:
        self.control_port = control_port
        self.server: ThreadingHTTPServer | None = None
        self.problem: str | None = None

    @property
    def running(self) -> bool:
        return self.server is not None

    def start(self) -> bool:
        if self.server is not None:
            return True
        handler = type("Handler", (_Handler,), {"control_port": self.control_port})
        try:
            self.server = ThreadingHTTPServer(("0.0.0.0", 80), handler)
        except OSError as exc:
            # Binding :80 needs root, and on a laptop something else usually has it. Not a
            # failure worth stopping for — the setup page is still reachable by address.
            self.problem = f"port 80 not available ({exc}); the portal is off"
            self.server = None
            return False
        threading.Thread(target=self.server.serve_forever, name="dicecore-portal",
                         daemon=True).start()
        self.problem = None
        return True

    def stop(self) -> None:
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.server = None


def auto_hotspot_wanted(mode: str, is_pi: bool) -> bool:
    """
    Whether this machine should ever open a network of its own.

    Defaulting to "on a Pi only" is not caution for its own sake. A desktop running DiceCore
    for development would, on this feature's own terms, seize the WiFi adapter and start
    serving an access point the first time a router rebooted for longer than the grace
    period. A dice reader must not be able to do that to somebody's computer.
    """
    if mode == "off":
        return False
    if mode == "always":
        return True
    return is_pi


def should_open_hotspot(online: bool, hotspot_running: bool, offline_since: float | None,
                        now: float, grace_s: float = DEFAULT_GRACE_S) -> bool:
    """
    Whether it is time for the box to serve its own network.

    Pure so the decision is testable without waiting a minute. The grace period is the whole
    subtlety: a router that reboots takes a network away for twenty seconds, and a box that
    drops its own connection to open an access point every time that happens is worse than
    one that waits.
    """
    if online or hotspot_running:
        return False
    if offline_since is None:
        return False
    return (now - offline_since) >= grace_s


class Watcher:
    """
    Watches the network and opens the box's own when there has been none for a while.

    The failure this exists for has no other exit: a box on a shelf that cannot reach the
    WiFi and has no screen cannot be told anything. Everything else — a wrong password, a
    moved router — is recoverable once there is *a* way in.
    """

    def __init__(self, network: Any, portal: CaptivePortal,
                 profile: Any = None, grace_s: float = DEFAULT_GRACE_S,
                 on_change: Callable[[str], None] | None = None) -> None:
        self.network = network
        self.portal = portal
        self.profile = profile
        self.grace_s = grace_s
        self.on_change = on_change
        self.offline_since: float | None = None
        self.last_action: str = ""
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="dicecore-network",
                                        daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self.portal.stop()

    def tick(self, now: float | None = None) -> str | None:
        """One look. Returns what it did, or None. Separated so a test can drive it."""
        now = time.time() if now is None else now
        try:
            status = self.network.status()
        except Exception:
            return None
        if not status.get("managed"):
            return None

        online = bool(status.get("online"))
        hotspot = bool(status.get("hotspot"))
        if online or hotspot:
            self.offline_since = None
        elif self.offline_since is None:
            self.offline_since = now

        if hotspot and not self.portal.running:
            self.portal.start()
        if not hotspot and self.portal.running:
            self.portal.stop()

        if should_open_hotspot(online, hotspot, self.offline_since, now, self.grace_s):
            ok, message = self.network.start_hotspot(self.profile)
            self.offline_since = None
            self.last_action = message
            if ok:
                self.portal.start()
            if self.on_change:
                self.on_change(message)
            return message
        return None

    def _run(self) -> None:
        while not self._stop.wait(CHECK_EVERY_S):
            self.tick()

    def describe(self) -> dict[str, Any]:
        return {"watching": self._thread is not None,
                "portal": self.portal.running,
                "portal_problem": self.portal.problem,
                "offline_since": self.offline_since,
                "last_action": self.last_action,
                "grace_s": self.grace_s}
