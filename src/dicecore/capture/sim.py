"""
Dice without dice.

Two situations want this. Somebody wants to play and has no tower yet — or no camera, or no
dice within reach. And two people want to play each other over the network without either of
them owning hardware. In both, the answer is the same: throw the dice in software.

**It renders a real picture and reads it back through the real engine.** That is more work
than returning six random numbers, and it is deliberate. One pipeline means the settling, the
game modes, the boards, the panel and the screens all behave exactly as they do with a
camera, and a bug in any of them shows up here rather than only on hardware. It also means
the play screen shows dice that were actually *seen*, which is the thing the whole project is
about.

Nothing is thrown until somebody asks. A camera watches a tray that changes on its own; a
simulator that rolled every time it was looked at would be a random number generator with a
picture attached.
"""

from __future__ import annotations

import random
from typing import Any

from ..dice import Frame, values_for
from .base import CaptureError, FrameSource


class SimSource(FrameSource):
    name = "sim"
    #: Not live: the same picture comes back until somebody throws again, which is exactly
    #: what a tray of settled dice looks like and what the frozen-feed check must not flag.
    is_live = False

    def __init__(self, width: int = 900, height: int = 600, die_px: int = 90,
                 seed: int | None = None) -> None:
        self.width, self.height, self.die_px = width, height, die_px
        self.rng = random.Random(seed)
        #: What the next throw consists of, set from the game mode by the reader.
        self.plan: list[str] = ["d6", "d6"]
        self._frame: Frame | None = None
        self._values: list[tuple[str, int]] = []
        self.throws = 0

    # --- what to throw ------------------------------------------------------
    def set_plan(self, kinds: list[str], count: int) -> None:
        """
        Decide the next throw's dice from the mode: which kinds, how many.

        Taken from the game rather than configured separately, because "Kniffel is five
        six-siders" is already written down once and a second copy is a second thing to get
        out of step.
        """
        kinds = [k for k in kinds if k in ("d2", "d3", "d4", "d6", "d8", "d10", "d100",
                                           "d12", "d20")] or ["d6"]
        count = max(1, min(12, count))
        # One kind: all the same. Several: the first is the workhorse and the rest appear
        # once each, which is what a roleplaying throw actually looks like.
        if len(kinds) == 1:
            self.plan = kinds * count
        else:
            self.plan = (kinds + [kinds[0]] * count)[:count]

    def throw(self) -> list[tuple[str, int]]:
        """Roll the planned dice and draw them. This is the button on the play screen."""
        self._values = [(kind, self.rng.choice(values_for(kind))) for kind in self.plan]
        self._frame = None
        self.throws += 1
        return list(self._values)

    # --- the source interface -----------------------------------------------
    def grab(self) -> Frame:
        if not self._values:
            # Nothing thrown yet. An empty tray is the honest picture, and the engine
            # reports "no dice" rather than the simulator inventing a roll nobody asked for.
            self._values = []
        if self._frame is None:
            self._frame = self._render()
        return self._frame

    def _render(self) -> Frame:
        from ..synth import render_scene

        image, _ = render_scene(self._values, width=self.width, height=self.height,
                                seed=self.rng.randrange(1 << 30), die_px=self.die_px)
        h, w = image.shape[:2]
        return Frame(image=image, source=f"sim:{self.throws}", size=(w, h))

    def describe(self) -> dict[str, Any]:
        return {"name": self.name, "plan": list(self.plan), "throws": self.throws,
                "showing": [{"kind": k, "value": v} for k, v in self._values],
                "width": self.width, "height": self.height}


def require_sim(source: FrameSource) -> SimSource:
    """The source as a simulator, or a sentence explaining that it is not one."""
    if not isinstance(source, SimSource):
        raise CaptureError(
            "Throwing from the screen only works with the simulator. Set the capture source "
            "to 'sim' under Setup → Camera — or throw real dice at the camera.")
    return source
