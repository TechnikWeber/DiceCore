"""
Rebooting the box from the page you are already standing at.

A CSI module only takes effect after a reboot, and the setup page is regularly the only way
into a DiceCore: no keyboard, no screen, and the person holding it is next to a dice tower
rather than an SSH client. Telling them "now reboot" and then offering no way to do it is a
dead end in the one workflow that cannot avoid a reboot.

Two things make this awkward enough to deserve its own module. The command has to be found
rather than assumed — `systemctl` is not on a Pi Zero image that boots without systemd, and
`shutdown` moved around between releases. And it must not run until the HTTP response is on
the wire: systemd starts tearing the machine down the moment it is asked, so an immediate
call makes a perfectly good reboot look like a network error and invites a second press.
"""

from __future__ import annotations

import shutil
import subprocess
import threading

#: Long enough for the response to reach the browser, short enough that nobody presses twice.
DELAY_S = 1.5

SERVICE = "dicecore.service"

#: Per action, the candidates in the order we prefer them. First one installed wins.
COMMANDS: dict[str, tuple[tuple[str, ...], ...]] = {
    "reboot": (("systemctl", "reboot"), ("shutdown", "-r", "now"), ("reboot",)),
    "service": (("systemctl", "restart", SERVICE),),
}


class PowerError(RuntimeError):
    """Says, in one sentence, why the machine cannot be restarted from here."""


def command_for(action: str) -> tuple[str, ...]:
    candidates = COMMANDS.get(action)
    if candidates is None:
        raise PowerError(f"Unknown restart action {action!r}. One of: "
                         + ", ".join(sorted(COMMANDS)))
    for argv in candidates:
        if shutil.which(argv[0]):
            return argv
    tools = ", ".join(sorted({argv[0] for argv in candidates}))
    raise PowerError(
        f"None of {tools} is installed, so DiceCore cannot restart this machine itself. "
        "Reboot it from a shell instead."
    )


def service_is_managed(run=subprocess.run) -> bool:
    """
    Whether systemd is actually running DiceCore.

    Restarting the service means asking systemd to start us again; a `dicecore serve` typed
    into a terminal would simply be killed and never come back, and the page would go dark
    for good. Better to refuse with a sentence than to take the box away.
    """
    if not shutil.which("systemctl"):
        return False
    try:
        done = run(["systemctl", "is-active", SERVICE], capture_output=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0


def schedule(action: str, delay_s: float = DELAY_S,
             timer=threading.Timer) -> tuple[str, ...]:
    """
    Arrange for the restart and return at once, so the caller can answer the browser first.

    The thread is a daemon on purpose: if the command never fires because the machine is
    already going down, nothing should be waiting on it.
    """
    if action == "service" and not service_is_managed():
        raise PowerError(
            f"{SERVICE} is not running under systemd, so there is nothing to restart — this "
            "DiceCore was started by hand. Stop it and start it again in that terminal."
        )
    argv = command_for(action)

    def fire() -> None:
        try:
            subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:  # pragma: no cover - the machine is on its way down either way
            pass

    thread = timer(delay_s, fire)
    thread.daemon = True
    thread.start()
    return argv
