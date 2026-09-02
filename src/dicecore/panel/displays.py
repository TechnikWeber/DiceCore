"""
The little screen over the tower.

Three families, one renderer: **ST7789** and **ILI9341** over SPI (colour), **SSD1306** over
I²C or SPI (monochrome). They are driven through luma, which speaks all three and takes a
PIL image — which is exactly what `render.py` produces, so a new panel is a table entry
rather than a new code path.

Every display also keeps its last frame as a PNG, whether or not any hardware is attached.
That is what lets the web UI show precisely what the screen over the tower is showing, and
what lets the whole feature be developed and tested on a laptop.
"""

from __future__ import annotations

import io
from typing import Any

from ..config import DisplaySettings
from .base import OutputDevice, OutputError
from .render import render
from .state import Presentation

#: id → (label, default size, monochrome, bus)
PANELS: dict[str, tuple[str, tuple[int, int], bool, str]] = {
    "preview": ("None — web preview only", (240, 240), False, "none"),
    "st7789": ("ST7789 colour LCD (SPI)", (240, 240), False, "spi"),
    "ili9341": ("ILI9341 colour LCD (SPI)", (320, 240), False, "spi"),
    "ssd1306": ("SSD1306 monochrome OLED (I²C)", (128, 64), True, "i2c"),
    "ssd1306-spi": ("SSD1306 monochrome OLED (SPI)", (128, 64), True, "spi"),
}

#: The sizes these panels are actually sold in, offered in the UI so nobody has to guess.
COMMON_SIZES = {
    "st7789": ((240, 240), (240, 320), (135, 240), (172, 320), (170, 320)),
    "ili9341": ((320, 240), (240, 320)),
    "ssd1306": ((128, 64), (128, 32)),
    "ssd1306-spi": ((128, 64), (128, 32)),
    "preview": ((240, 240), (320, 240), (128, 64)),
}


class DisplayOutput(OutputDevice):
    name = "display"
    animates = True

    def __init__(self, settings: DisplaySettings) -> None:
        self.settings = settings
        panel = PANELS.get(settings.kind)
        if panel is None:
            raise OutputError(f"Unknown display {settings.kind!r}. One of: "
                              + ", ".join(PANELS))
        self.label, default_size, self.mono, self.bus = panel
        self.size = (settings.width or default_size[0], settings.height or default_size[1])
        self.last_png: bytes | None = None
        self.problem: str | None = None
        self._device: Any = None
        if settings.kind != "preview":
            try:
                self._device = self._open()
            except OutputError as exc:
                # A panel that will not come up must not stop the dice being read. The web
                # preview keeps working and the UI shows the reason.
                self.problem = str(exc)

    # --- hardware -----------------------------------------------------------
    def _serial(self) -> Any:
        settings = self.settings
        try:
            from luma.core.interface.serial import i2c, spi
        except ImportError as exc:
            raise OutputError(
                "The display stack is not installed: `pip install 'dicecore[display]'`."
            ) from exc
        try:
            if self.bus == "i2c":
                return i2c(port=settings.i2c_port, address=int(settings.i2c_address, 0))
            return spi(port=settings.spi_port, device=settings.spi_device,
                       gpio_DC=settings.gpio_dc, gpio_RST=settings.gpio_rst)
        except Exception as exc:
            # Distinguish "no Pi here" from "wired wrong": the first is the normal case on a
            # laptop and needs no advice about raspi-config, and printing the wrong one of
            # these sends people looking for a fault that is not there.
            if isinstance(exc, ImportError) or "No module named" in str(exc):
                raise OutputError(
                    f"No GPIO on this machine, so the {self.label} cannot be driven here "
                    f"({exc}). The preview below still shows what the panel would display."
                ) from exc
            raise OutputError(
                f"The {self.label} did not answer on {self.bus.upper()}: {exc}. Check that "
                f"the bus is enabled (raspi-config → Interface Options) and that the wiring "
                f"matches the pins set here."
            ) from exc

    def _open(self) -> Any:
        kind = self.settings.kind
        try:
            if kind in ("ssd1306", "ssd1306-spi"):
                from luma.oled.device import ssd1306

                device = ssd1306(self._serial(), width=self.size[0], height=self.size[1],
                                 rotate=self.settings.rotate)
            elif kind == "st7789":
                from luma.lcd.device import st7789

                device = st7789(self._serial(), width=self.size[0], height=self.size[1],
                                rotate=self.settings.rotate)
            elif kind == "ili9341":
                from luma.lcd.device import ili9341

                device = ili9341(self._serial(), width=self.size[0], height=self.size[1],
                                 rotate=self.settings.rotate)
            else:
                return None
        except OutputError:
            raise
        except ImportError as exc:
            raise OutputError(
                "The display stack is not installed: `pip install 'dicecore[display]'`."
            ) from exc
        except Exception as exc:
            hint = ("Check that I²C is enabled (raspi-config → Interface Options), that the "
                    f"address matches (`i2cdetect -y {self.settings.i2c_port}`), and that the "
                    "panel has power.") if self.bus == "i2c" else (
                    "Check that SPI is enabled (raspi-config → Interface Options) and that "
                    "the DC and reset pins match the wiring.")
            raise OutputError(f"The {self.label} could not be started: {exc}. {hint}") from exc
        try:
            device.contrast(max(0, min(255, self.settings.contrast)))
        except Exception:
            pass  # not every panel has a contrast register worth arguing about
        return device

    # --- showing ------------------------------------------------------------
    def present(self, presentation: Presentation) -> None:
        try:
            image = render(presentation, self.size, self.mono)
        except ImportError as exc:
            self.problem = f"Pillow is not installed, so nothing can be drawn: {exc}"
            return
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, format="PNG")
        self.last_png = buffer.getvalue()
        if self._device is not None:
            try:
                self._device.display(image)
            except Exception as exc:
                self.problem = f"The display stopped responding: {exc}"
                self._device = None

    def close(self) -> None:
        if self._device is not None:
            try:
                self._device.cleanup()
            except Exception:
                pass
            self._device = None

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name, "kind": self.settings.kind, "label": self.label,
            "width": self.size[0], "height": self.size[1], "mono": self.mono,
            "bus": self.bus, "attached": self._device is not None, "problem": self.problem,
        }
