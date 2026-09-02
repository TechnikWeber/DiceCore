"""
Where this DiceCore can be reached.

The host screen shows an address for other people to type in, so it has to be an address
that actually works from another machine. The two obvious answers are both wrong: the
configured port is not necessarily the port it was started on, and `localhost` is the one
address that is guaranteed *not* to work for anybody else.

No dependencies — this runs on the Pi Zero as well.
"""

from __future__ import annotations

import socket

#: Asking the routing table where a packet would leave from. Nothing is sent: connecting a
#: UDP socket only picks an interface, which is exactly the question being asked. The
#: Tailscale one is a separate probe because a machine on both has two useful addresses and
#: the other players may only be on one of them.
PROBES = ("8.8.8.8", "100.100.100.100")


def _outbound(target: str) -> str | None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect((target, 9))
        return str(sock.getsockname()[0])
    except OSError:
        return None
    finally:
        sock.close()


def hostnames() -> list[str]:
    """The machine's own names. `.local` is offered because that is how a Pi is found."""
    try:
        name = socket.gethostname()
    except OSError:
        return []
    names = [name] if name and name != "localhost" else []
    if names and "." not in name:
        names.append(f"{name}.local")
    return names


def addresses(port: int) -> list[str]:
    """Every `host:port` another DiceCore could plausibly reach this one at, best first."""
    found: list[str] = []
    # An address first: it works from anything on the network. A `.local` name needs mDNS,
    # which not every machine has, so it is offered as an alternative rather than as *the*
    # answer — even though it is the nicer one to read out loud.
    for probe in PROBES:
        ip = _outbound(probe)
        if ip and not ip.startswith("127.") and f"{ip}:{port}" not in found:
            found.append(f"{ip}:{port}")
    for name in hostnames():
        found.append(f"{name}:{port}")
    return found
