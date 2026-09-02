"""
Two buttons on the header, because a game needs answers a camera cannot give.

"I am keeping these three." "Spend a chip." "My turn is over." None of that is visible on
the tray, and walking round to a browser to say it defeats the point of a machine that reads
your dice for you. So: a chip button and a next-turn button, both optional, both settable to
`-1` when the browser is enough.

Wired the ordinary way — button between the pin and ground, using the Pi's own pull-up — so
there is nothing to build but two buttons.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from ..config import SignalSettings


class _Input:
    """One button, or the memory of one when there is no GPIO here."""

    def __init__(self, number: int, pull_up: bool, debounce_s: float,
                 pressed: Callable[[], None]) -> None:
        self.number = number
        self.presses = 0
        self.simulated = True
        self.last_press = 0.0
        self._callback = pressed
        self._device: Any = None
        if number < 0:
            return
        try:
            import warnings

            with warnings.catch_warnings():
                # Off a Pi, gpiozero warns once per pin factory it cannot find. Expected.
                warnings.simplefilter("ignore")
                from gpiozero import Button

                self._device = Button(number, pull_up=pull_up, bounce_time=debounce_s)
            self._device.when_pressed = lambda _=None: self.press()
            self.simulated = False
        except Exception:
            self._device = None

    def press(self) -> None:
        """Fire the action. Also the path a browser press takes, so both behave the same."""
        self.presses += 1
        self.last_press = time.time()
        try:
            self._callback()
        except Exception:
            # A game that throws must not take the button — or the service — down with it.
            pass

    def close(self) -> None:
        if self._device is not None:
            try:
                self._device.close()
            except Exception:
                pass
            self._device = None

    def to_json(self) -> dict[str, Any]:
        return {"pin": self.number, "presses": self.presses, "simulated": self.simulated,
                "last_press": self.last_press}


class ButtonPanel:
    """The header's inputs. Handlers are set by whoever owns the game."""

    def __init__(self, settings: SignalSettings, on_chip: Callable[[], None],
                 on_next: Callable[[], None]) -> None:
        self.settings = settings
        self.chip = _Input(settings.chip_pin, settings.button_pull_up,
                           settings.debounce_s, on_chip)
        self.next = _Input(settings.next_pin, settings.button_pull_up,
                           settings.debounce_s, on_next)

    @property
    def any_wired(self) -> bool:
        return any(button.number >= 0 for button in (self.chip, self.next))

    def close(self) -> None:
        self.chip.close()
        self.next.close()

    def describe(self) -> dict[str, Any]:
        simulated = self.any_wired and all(
            b.simulated for b in (self.chip, self.next) if b.number >= 0)
        return {
            "chip": self.chip.to_json(), "next": self.next.to_json(),
            "wired": self.any_wired,
            "problem": ("No GPIO here, so the buttons are simulated — the browser's own "
                        "buttons do the same thing.") if simulated else None,
        }
