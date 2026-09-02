# The screen, the lamps and the buzzer

A number that only exists inside an API is not much use at a table. DiceCore can put the
result on a small screen over the tower and tell you with two lamps whose turn it is.

Both are optional, both can run at once, and **both work before anything is soldered**: the
web UI renders exactly what the panel would show and lights the lamps on screen, so the
layout and the wiring plan can be worked out on a laptop.

> There is a second reason for the screen, beyond convenience. A number that appears the
> instant the dice stop is **public**: everyone has already read it, so turning a die over
> afterwards changes nothing anybody believes. That does more against casual cheating than
> watching the tray does — see [ANTI-CHEAT.md](ANTI-CHEAT.md).

![Five panels side by side, rendered by DiceCore itself: an ST7789 240x240 showing NICE ROLL over a 20 with rings behind it, an ILI9341 320x240 showing HANDS OFF over 18, a narrow ST7789 135x240 showing VOID in red, and two SSD1306 OLEDs — 128x64 stacked and 128x32 on one line](screenshots/displays.png)

## What it shows

| Phase | Screen | Green | Red | Buzzer |
|---|---|---|---|---|
| idle | *throw* | ● | | |
| rolling | … | | ● | |
| reading | … | | ● | |
| **result** | **the number** + HANDS OFF | | ● | one beep |
| **ready** | the number + THROW AGAIN | ● | | short beep |
| void | the number, struck through, VOID | | flashing | long buzz |

The number stays on the screen from the moment it is read until the next throw. Only the
caption and the lamps change — the screen never goes blank between rolls, and never shows a
number the tray no longer agrees with.

A natural maximum on any die gets a short animation (expanding rings, or the whole panel
inverting on a monochrome one) and a three-note beep. A natural 1 gets a flat grey screen
and one long note. Both are configurable, and a die the engine could not read never
celebrates — a party over a number the machine did not understand is worse than silence.

## Supported panels

| Panel | Bus | Sizes offered | Notes |
|---|---|---|---|
| **ST7789** | SPI | 240×240, 240×320, 135×240, 172×320, 170×320 | The common round-cornered colour LCDs |
| **ILI9341** | SPI | 320×240, 240×320 | The classic 2.4"/2.8" colour panel |
| **SSD1306** | I²C *or* SPI | 128×64, 128×32 | The cheap monochrome OLED |
| *None* | — | any | Web preview only, for working without hardware |

Any size can be typed in; the list is what these panels are actually sold as. The layout is
measured, not assumed, so a 135×240 stick and a 320×240 tile both come out looking
deliberate rather than cropped.

Driven through [luma](https://luma-lcd.readthedocs.io), which takes a PIL image — so adding
a panel luma supports is a table entry in `output/displays.py`, not a new code path.

### Wiring a SPI panel (ST7789 / ILI9341)

| Panel | Pi (BCM) | Physical pin |
|---|---|---|
| VCC | 3V3 | 1 |
| GND | GND | 6 |
| SCL / SCK | GPIO 11 (SCLK) | 23 |
| SDA / MOSI | GPIO 10 (MOSI) | 19 |
| CS | GPIO 8 (CE0) | 24 |
| DC | GPIO 25 | 22 |
| RST | GPIO 24 | 18 |
| BLK / LED | 3V3 | 17 |

`sudo raspi-config` → *Interface Options* → *SPI* → enable, then reboot. DC and RST are
settings, so pick different pins if these clash with your lamps.

### Wiring an SSD1306 (I²C)

| Panel | Pi (BCM) | Physical pin |
|---|---|---|
| VCC | 3V3 | 1 |
| GND | GND | 9 |
| SDA | GPIO 2 | 3 |
| SCL | GPIO 3 | 5 |

Enable I²C the same way, then `i2cdetect -y 1` should show the panel — usually at `0x3C`,
sometimes `0x3D`. That address is a setting.

## The lamps and the buzzer

Three GPIOs, all optional, any of them settable to `-1` to leave that one out:

| Signal | Default pin (BCM) | Physical | Means |
|---|---|---|---|
| Green LED | 17 | 11 | Throw whenever you like |
| Red LED | 27 | 13 | The tray is being read or watched — hands off |
| Buzzer | 22 | 15 | The number is in; and your turn has come round |

Wire each LED **through a resistor** (220–470 Ω) to ground, long leg to the GPIO. A passive
buzzer needs a transistor; an active buzzer module can usually sit straight on the pin — and
if yours is one of the boards that switches on when the pin goes *low*, turn off **Pin is
active high**.

This is the honest reason the lamps exist: at a table, nobody looks at a screen to find out
whether it is their turn. They look up, see green, and throw.

## Setting it up

**Screen & lamps** in the web UI. The **Run through the phases** button walks the whole
sequence — rolling, reading, result, your turn — so you can check the wiring with a
screwdriver in your hand and without throwing anything. The individual buttons next to it
jump straight to one phase.

The panel preview under *Display* is rendered whether or not hardware is attached, and it is
the same renderer that drives the real panel, so what you see there is what the tower shows.

```bash
# On the Pi
sudo raspi-config          # enable SPI and/or I2C
pip install 'dicecore[display,gpio]'
```

If a panel does not come up, DiceCore says so in the UI and keeps going — a screen that
will not start must never stop the dice being read.

## From your own code

The state that drives both outputs is public, so a project embedding DiceCore can show the
same thing its own way:

```python
from dicecore.output import OutputHub
from dicecore.output.state import Presentation, RESULT
from dicecore.reader import Reader

hub = OutputHub(settings.output)
reader = Reader(settings, on_phase=hub.update)   # every phase change, screen and lamps
```

`Presentation` carries the phase, the number, the notation, the verdict and whether it is a
celebration; `presentation.go` is the one boolean the green lamp is: *may I throw?*
