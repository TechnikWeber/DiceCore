"""
Playing against another DiceCore.

One instance is the table and owns the game; the others are guests that mirror it and ask
for things. Each player throws on their own tray — their own camera, or their own simulator —
and the dice go up the wire, so nobody has to share a tower.

`protocol.py` is what they say to each other and is pure; `host.py` and `guest.py` are the
two ends.
"""

from .guest import Guest, table_url
from .host import Table
from .protocol import VERSION, Seat
from .reach import addresses

__all__ = ["Table", "Guest", "Seat", "VERSION", "table_url", "addresses"]
