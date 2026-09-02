"""
Two lamps and a buzzer.

The question a screen answers badly from across a table: *is it my turn yet?* A green LED
answers it without anybody reading anything. Red means the tray is being read or watched —
hands off. The buzzer marks the two moments worth hearing: the number is in, and you may
throw again.

Wired through gpiozero, which is on every Raspberry Pi OS image, and which falls back to a
recorded simulation when there are no pins — so the web UI shows the lamps whether or not
anything is soldered yet.
"""

from __future__ import annotations

import time
from typing import Any

from ..config import SignalSettings
from .base import OutputDevice
from .state import ERROR, READY, RESULT, VOID, Presentation

#: phase → (green, red). Green is "throw"; red is "leave the tray alone".
LAMPS = {
    "idle": (True, False),
    "rolling": (False, True),
    "reading": (False, True),
    RESULT: (False, True),      # number is in, but the tray is still being watched
    READY: (True, False),
    VOID: (False, True),
    ERROR: (False, True),
}


class _Pin:
    """One output pin, or the memory of one when there is no GPIO here."""

    def __init__(self, number: int, active_high: bool) -> None:
        self.number = number
        self.active_high = active_high
        self.state = False
        self.simulated = True
        self._device: Any = None
        if number < 0:
            return
        try:
            import warnings

            with warnings.catch_warnings():
                # Off a Pi, gpiozero warns once per pin factory it cannot find. That is the
                # expected case here and the UI reports it properly, so it is not news.
                warnings.simplefilter("ignore")
                from gpiozero import LED

                self._device = LED(number, active_high=active_high)
            self.simulated = False
        except Exception:
            # No pins here, or they are in use. The simulation keeps the UI honest and the
            # reason is reported by `SignalOutput.describe`.
            self._device = None

    def set(self, on: bool) -> None:
        if self.state == on:
            return
        self.state = on
        if self._device is not None:
            self._device.on() if on else self._device.off()

    def close(self) -> None:
        if self._device is not None:
            try:
                self._device.close()
            except Exception:
                pass
            self._device = None


class SignalOutput(OutputDevice):
    name = "signals"
    animates = True

    def __init__(self, settings: SignalSettings) -> None:
        self.settings = settings
        self.green = _Pin(settings.green_pin, settings.active_high)
        self.red = _Pin(settings.red_pin, settings.active_high)
        self.buzzer = _Pin(settings.buzzer_pin if settings.buzzer_enabled else -1,
                           settings.active_high)
        self._last_phase: str | None = None
        #: What the buzzer last did, so the UI can show it.
        self.last_sound = ""

    @property
    def simulated(self) -> bool:
        return self.green.simulated and self.red.simulated

    def present(self, presentation: Presentation) -> None:
        green, red = LAMPS.get(presentation.phase, (False, False))
        if presentation.phase == VOID:
            # A voided roll flashes rather than sitting there red, because it is the one
            # state somebody has to actually notice.
            red = presentation.anim % 2 == 0
        self.green.set(green)
        self.red.set(red)

        if presentation.phase != self._last_phase:
            self._sound_for(presentation)
            self._last_phase = presentation.phase

    def _sound_for(self, presentation: Presentation) -> None:
        """One short pattern per phase change. Nothing loops; nothing nags."""
        beep = self.settings.beep_ms / 1000.0
        if presentation.phase == RESULT:
            if presentation.celebrate and self.settings.celebrate_sound:
                self._pattern([beep, beep, beep * 2], "nice roll")
            elif presentation.lament and self.settings.celebrate_sound:
                self._pattern([beep * 4], "ouch")
            else:
                self._pattern([beep], "result")
        elif presentation.phase == READY:
            self._pattern([beep * 0.5], "your turn")
        elif presentation.phase == VOID:
            self._pattern([beep * 6], "void")
        elif presentation.phase == ERROR:
            self._pattern([beep, beep], "problem")

    def _pattern(self, beeps: list[float], label: str) -> None:
        self.last_sound = label
        if self.buzzer.number < 0:
            return
        for index, length in enumerate(beeps):
            if index:
                time.sleep(0.05)
            self.buzzer.set(True)
            time.sleep(length)
            self.buzzer.set(False)

    def close(self) -> None:
        for pin in (self.green, self.red, self.buzzer):
            pin.set(False)
            pin.close()

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "simulated": self.simulated,
            "green": {"pin": self.green.number, "on": self.green.state},
            "red": {"pin": self.red.number, "on": self.red.state},
            "buzzer": {"pin": self.buzzer.number, "last": self.last_sound},
            "problem": (
                "No GPIO here, so the lamps are simulated — the web UI shows what they would "
                "be doing. On a Pi, install the 'gpio' extra."
            ) if self.simulated else None,
        }
