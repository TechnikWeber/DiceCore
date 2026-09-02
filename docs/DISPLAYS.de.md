[English](DISPLAYS.md) · **Deutsch**

# Der Bildschirm, die Lampen und der Summer

Eine Zahl, die nur in einer API existiert, nützt an einem Tisch wenig. DiceCore kann das
Ergebnis auf ein kleines Display über dem Turm bringen und dir mit zwei Lampen sagen, wer dran
ist.

Beides ist optional, beides kann gleichzeitig laufen, und **beides funktioniert, bevor etwas
gelötet ist**: die Weboberfläche zeichnet genau das, was das Panel zeigen würde, und schaltet
die Lampen auf dem Bildschirm — Layout und Verdrahtungsplan lassen sich also auf einem Laptop
ausarbeiten.

> Für das Display gibt es einen zweiten Grund über die Bequemlichkeit hinaus. Eine Zahl, die
> in dem Moment erscheint, in dem die Würfel liegen bleiben, ist **öffentlich**: alle haben
> sie schon gelesen, einen Würfel danach umzudrehen ändert also nichts an dem, was irgendwer
> glaubt. Das tut gegen Gelegenheitsschummelei mehr als das Beobachten der Fläche — siehe
> [ANTI-CHEAT.de.md](ANTI-CHEAT.de.md).

![Fünf Panels nebeneinander, von DiceCore selbst gezeichnet: ein ST7789 240x240 mit NICE ROLL über einer 20 und Ringen dahinter, ein ILI9341 320x240 mit HANDS OFF über 18, ein schmaler ST7789 135x240 mit VOID in Rot, und zwei SSD1306-OLEDs — 128x64 gestapelt und 128x32 einzeilig](screenshots/displays.png)

## Was es zeigt

| Phase | Bildschirm | Grün | Rot | Summer |
|---|---|---|---|---|
| idle | *throw* | ● | | |
| rolling | … | | ● | |
| reading | … | | ● | |
| **result** | **die Zahl** + HANDS OFF | | ● | ein Piep |
| **ready** | die Zahl + THROW AGAIN | ● | | kurzer Piep |
| void | die Zahl, durchgestrichen, VOID | | blinkt | langer Summton |

Die Zahl bleibt vom Lesen bis zum nächsten Wurf auf dem Bildschirm. Nur die Beschriftung und
die Lampen wechseln — der Bildschirm wird zwischen Würfen nie leer und zeigt nie eine Zahl,
mit der die Fläche nicht mehr übereinstimmt.

Ein natürliches Maximum auf irgendeinem Würfel bekommt eine kurze Animation (sich ausbreitende
Ringe, oder das ganze Panel invertiert auf einem monochromen) und einen Dreiklang. Eine
natürliche 1 bekommt einen flachen grauen Bildschirm und einen langen Ton. Beides ist
einstellbar, und ein Würfel, den die Erkennung nicht lesen konnte, feiert nie — eine Party um
eine Zahl, die die Maschine nicht verstanden hat, ist schlimmer als Stille.

## Unterstützte Panels

| Panel | Bus | Angebotene Größen | Anmerkungen |
|---|---|---|---|
| **ST7789** | SPI | 240×240, 240×320, 135×240, 172×320, 170×320 | Die verbreiteten Farb-LCDs mit runden Ecken |
| **ILI9341** | SPI | 320×240, 240×320 | Das klassische 2,4"/2,8"-Farbpanel |
| **SSD1306** | I²C *oder* SPI | 128×64, 128×32 | Das billige monochrome OLED |
| *Keines* | — | beliebig | Nur Web-Vorschau, zum Arbeiten ohne Hardware |

Jede Größe lässt sich eintippen; die Liste ist, wie diese Panels tatsächlich verkauft werden.
Das Layout wird ausgemessen, nicht angenommen, also sehen ein 135×240-Streifen und eine
320×240-Kachel beide absichtlich aus statt beschnitten.

Angesteuert über [luma](https://luma-lcd.readthedocs.io), das ein PIL-Bild entgegennimmt — ein
von luma unterstütztes Panel hinzuzufügen ist also ein Tabelleneintrag in `panel/displays.py`,
kein neuer Codepfad.

### Ein SPI-Panel verdrahten (ST7789 / ILI9341)

| Panel | Pi (BCM) | Physischer Pin |
|---|---|---|
| VCC | 3V3 | 1 |
| GND | GND | 6 |
| SCL / SCK | GPIO 11 (SCLK) | 23 |
| SDA / MOSI | GPIO 10 (MOSI) | 19 |
| CS | GPIO 8 (CE0) | 24 |
| DC | GPIO 25 | 22 |
| RST | GPIO 24 | 18 |
| BLK / LED | 3V3 | 17 |

`sudo raspi-config` → *Interface Options* → *SPI* → einschalten, dann neu starten. DC und RST
sind Einstellungen, nimm also andere Pins, falls diese mit deinen Lampen kollidieren.

### Ein SSD1306 verdrahten (I²C)

| Panel | Pi (BCM) | Physischer Pin |
|---|---|---|
| VCC | 3V3 | 1 |
| GND | GND | 9 |
| SDA | GPIO 2 | 3 |
| SCL | GPIO 3 | 5 |

I²C genauso einschalten, dann sollte `i2cdetect -y 1` das Panel zeigen — meist auf `0x3C`,
manchmal `0x3D`. Diese Adresse ist eine Einstellung.

## Die Lampen und der Summer

Drei GPIOs, alle optional, jeder einzelne auf `-1` setzbar, um ihn wegzulassen:

| Signal | Standard-Pin (BCM) | Physisch | Bedeutet |
|---|---|---|---|
| Grüne LED | 17 | 11 | Wirf, wann immer du willst |
| Rote LED | 27 | 13 | Die Fläche wird gelesen oder beobachtet — Hände weg |
| Summer | 22 | 15 | Die Zahl steht; und du bist wieder an der Reihe |

Jede LED **über einen Widerstand** (220–470 Ω) nach Masse, langes Bein an den GPIO. Ein
passiver Summer braucht einen Transistor; ein aktives Summermodul darf meist direkt an den Pin
— und wenn deins zu den Platinen gehört, die bei *low* einschalten, schalt **Pin is active
high** aus.

Das ist der ehrliche Grund für die Lampen: an einem Tisch schaut niemand auf einen Bildschirm,
um herauszufinden, ob er dran ist. Man schaut hoch, sieht grün und wirft.

## Einrichten

**Screen & lamps** in der Weboberfläche. Der Knopf **Run through the phases** läuft die ganze
Abfolge durch — rollen, lesen, Ergebnis, du bist dran —, damit du die Verdrahtung mit dem
Schraubendreher in der Hand prüfen kannst, ohne etwas zu werfen. Die Einzelknöpfe daneben
springen direkt in eine Phase.

Die Panel-Vorschau unter *Display* wird gezeichnet, ob Hardware angeschlossen ist oder nicht,
und es ist derselbe Zeichner, der das echte Panel treibt — was du dort siehst, zeigt also auch
der Turm.

```bash
# Auf dem Pi
sudo raspi-config          # SPI und/oder I2C einschalten
pip install 'dicecore[display,gpio]'
```

Wenn ein Panel nicht hochkommt, sagt DiceCore das in der Oberfläche und macht weiter — ein
Bildschirm, der nicht startet, darf niemals das Lesen der Würfel aufhalten.

## Aus eigenem Code

Der Zustand, der beide Ausgaben treibt, ist öffentlich, ein Projekt, das DiceCore einbindet,
kann dasselbe also auf seine eigene Art zeigen:

```python
from dicecore.panel import OutputHub
from dicecore.panel.state import Presentation, RESULT
from dicecore.reader import Reader

hub = OutputHub(settings.output)
reader = Reader(settings, on_phase=hub.update)   # jeder Phasenwechsel, Bildschirm und Lampen
```

`Presentation` trägt die Phase, die Zahl, die Notation, das Urteil und ob gefeiert wird;
`presentation.go` ist der eine Wahrheitswert, der die grüne Lampe ist: *darf ich werfen?*
