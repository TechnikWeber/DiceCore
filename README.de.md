[English](README.md) · **Deutsch**

# DiceCore

**Liest echte Würfel mit einer Kamera.** Ein Raspberry Pi schaut von oben auf die
Landefläche eines Würfelturms und macht aus dem, was dort liegt, Daten: wie viele Würfel,
welcher Art, mit welchem Wert, und was das zusammen ergibt — als Zahl auf dem Bildschirm,
als JSON-API und als Live-Stream, den ein Bot oder ein Spiel abonnieren kann.

> **Status: früh. Nichts davon lief bisher an einem echten Turm.** Die Kette funktioniert
> Ende zu Ende auf synthetischen und simulierten Bildern — Aufnahme, Ruhe-Erkennung,
> Augenzählen, die Label-Schleife, die API und die Weboberfläche sind da und getestet. Es
> fehlt ein trainiertes Modell (dafür braucht es echte Würfel vor einer echten Kamera) und
> jeder Hardware-Pfad, der sich nur auf einem Pi überprüfen lässt.
> [docs/CONCEPT.md](docs/CONCEPT.md) ist die Referenz für das Ziel,
> [docs/HARDWARE.md](docs/HARDWARE.md) sagt, was zu kaufen ist und wohin es gehört.

![Der Reiter „Roll“: die Summe, die Notation, pro Würfel ein Chip mit Konfidenz, und darunter das aufgenommene Bild mit dem erkannten Würfel als beschriftetem Kasten](docs/screenshots/roll.jpg)

## Was heute funktioniert

- **Augenwürfel lesen ganz ohne Training.** Die Würfel werden gegen die Landefläche
  freigestellt, die Augen gezählt, die Summe ausgegeben. Auf synthetischen Szenen exakt; auf
  echten braucht es angepasste Tray- und Kontrasteinstellungen — dafür ist der Reiter
  **Detection** da.
- **Ehrliches Scheitern.** Vielseitige Würfel werden *gefunden* und als ungelesen gemeldet,
  statt geraten zu werden. Eine selbstbewusst falsche Zahl ist schlimmer als „dafür brauche
  ich ein Modell".
- **Fair Play.** Nach dem Lesen wird die Landefläche weiter beobachtet. Eine Hand, die
  hineingreift, wird protokolliert; Würfel, die *nicht mehr das zeigen, was gelesen wurde*,
  machen den Wurf ungültig. Erkannt werden: ein nachträglich umgedrehter Würfel, ein
  hinzugelegter oder verschwundener, derselbe Glückswurf zweimal gemeldet, ein eingefrorenes
  Videobild und eine abgedeckte Linse — und es sagt offen, dass es
  [Manipulations*nachweis*, kein Manipulations*schutz*](docs/ANTI-CHEAT.md) ist.
- **Eine Label-Schleife statt eines Label-Werkzeugs.** Würfeln, hinschauen, korrigieren,
  bestätigen — jeder bestätigte Wurf ist ein Trainingsbeispiel, im Browser, ohne Kommandozeile.
- **Training aus dem Browser**, mit laufender Loss- und Genauigkeitsanzeige, am Ende ein
  ONNX-Modell, das die Engine übernimmt. Training braucht PyTorch und läuft deshalb auf dem
  PC; die Oberfläche sagt das offen, statt auf halbem Weg abzubrechen.
- **Ein Spielbildschirm und eine Einrichtungsseite.** `/` ist das Brett für den Fernseher —
  die Zahl groß, die Würfel gezeichnet, der Wurfzähler, der Spielblock. `/setup` ist alles
  andere. Ein Dienst, ein Repo, zwei Eingänge.
- **Züge, Halten und Chips.** Kniffel sind drei Würfe mit Behalten dazwischen: DiceCore
  zählt sie herunter, erkennt welche Würfel liegen geblieben sind, und ein Chip kauft einen
  vierten. Zwei optionale GPIO-Taster tun dasselbe ohne Browser.
- **Spielmodi.** Dieselben Würfel, gelesen wie das Spiel an deinem Tisch sie liest: als
  Summe, als Anzahl Erfolge, als Kniffel-Kombination, als Prozentwurf, als Unterwürfeln
  gegen einen Zielwert. Vierzehn Stück, von normalen Sechsseitern bis zum Chi-Quadrat-Test,
  ob ein Würfel gezinkt ist — plus *Selbst bauen* für das Spiel, das nicht dabei ist.
- **Ein Display und zwei Lampen.** ST7789, ILI9341 oder SSD1306 über dem Turm zeigt die Zahl,
  sobald die Würfel liegen, mit kleiner Animation bei einer natürlichen 20; eine grüne und
  eine rote LED plus Summer sagen, wer dran ist, ganz ohne Hinsehen. Beides optional, beides
  gleichzeitig nutzbar, und beides im Browser vorschaubar, bevor ein einziger Draht gelötet ist.
- **Eine versionierte API** und ein WebSocket-Stream, gedacht zum Einbinden in andere Projekte.
- **CSI-Kameramodule als Einstellung** — inklusive Arducam IMX519 / 64MP / Owlsight /
  Pivariety, die ein Pi nicht selbst erkennt. Die Auswahl in der Oberfläche schreibt den
  `dtoverlay` in die `config.txt` und sagt, dass neu gestartet werden muss.
- **Alles davon ohne Hardware.** `dicecore synth` zeichnet Würfel, die Quelle `folder` spielt
  sie ab, und alles oben Genannte läuft damit auf dem Laptop.

![Der Spielbildschirm während eines Kniffel-Zugs: die Kombination groß, die fünf Würfel als Augen gezeichnet, der Wurfzähler mit Chips und rechts der Spielblock](docs/screenshots/play.jpg)

![Fünf Panels nebeneinander, von DiceCore selbst gerendert: ein ST7789 240x240 mit NICE ROLL über einer 20, ein ILI9341 320x240 mit HANDS OFF über 18, ein schmales ST7789 135x240 mit rotem VOID und zwei SSD1306-OLEDs](docs/screenshots/displays.png)

*Derselbe Renderer bedient jedes Panel und die Browser-Vorschau — das Layout lässt sich
festlegen, bevor irgendetwas gelötet ist.*

![Der Reiter „Training“: gespeicherte Würfe, pro Würfel die Schätzung der Engine vorausgefüllt, bereit zum Korrigieren und Bestätigen](docs/screenshots/training.jpg)

## Fünf Minuten, ohne Hardware

```bash
git clone https://github.com/TechnikWeber/DiceCore && cd DiceCore
python3 -m venv .venv && .venv/bin/pip install -e '.[vision,server,dev]'

.venv/bin/dicecore synth --count 20 --kinds d6,d20   # erfundene Würfe zum Lesen
.venv/bin/dicecore serve                             # → http://localhost:8099/
```

`/` ist der Spielbildschirm, `/setup` die Werkstatt.

Danach `curl localhost:8099/api/v1/roll`:

```json
{"dice": [{"kind": "d6", "value": 3, "confidence": 0.99, "box": {"x": 88, "y": 154, "w": 98, "h": 98}}],
 "total": 3, "count": 1, "notation": "1d6 → 3", "engine": "classic", "warnings": [],
 "verdict": "clean", "usable": true, "stale": false}
```

Die Zahl kommt rund eine fünftel Sekunde nachdem die Würfel liegen — die Fair-Play-Wache
läuft dahinter weiter, das Urteil landet ein paar Sekunden später auf `/api/v1/state` und im
WebSocket. `?verify=1` wartet stattdessen darauf.

## Auf dem Raspberry Pi

```bash
sudo apt install rpicam-apps python3-picamera2
git clone https://github.com/TechnikWeber/DiceCore && cd DiceCore
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -e '.[vision,server]'
.venv/bin/dicecore doctor      # was dieser Pi kann und was nicht
.venv/bin/dicecore serve
```

`doctor` lohnt sich vor allem anderen: Auf einem **Pi Zero v1 oder Pi 3 (ARMv6)** gibt es
kein OpenCV und kein onnxruntime, und genau das sagt er. Das ist keine Sackgasse — ohne
Extras installieren, `engine.mode=remote` setzen und auf einen PC oder Pi 5 zeigen lassen,
auf dem DiceCore ebenfalls läuft. Der Pi nimmt auf, die andere Maschine liest, und die API
antwortet in beiden Fällen identisch.

## Wie das zusammenhängt

```
Aufnahme ───────────► Engine ──────────► Ausgaben
picamera2 / rpicam    classic (Augen)    HTTP JSON  /api/v1/roll
v4l2 / folder / push  model (ONNX)       WebSocket  /api/v1/events
                      remote (ein        Weboberfläche
   │                   anderer Knoten)   dein Bot, dein Spiel
   └──► Datensatz ─► Training ─► model.onnx ──┘
```

Jeder Kasten ist über Einstellungen austauschbar, und jeder hat eine Umsetzung, die ohne
Hardware funktioniert. Siehe [docs/CONCEPT.md](docs/CONCEPT.md).

## Aus einem anderen Projekt heraus benutzen

Genau dafür ist das gedacht — siehe [docs/API.md](docs/API.md).

```python
import requests
roll = requests.get("http://dicecore.local:8099/api/v1/roll", timeout=15).json()
if roll["usable"]:                               # falsch nur bei manipulierter Landefläche
    print(roll["notation"], "=", roll["total"])  # 1d6+1d20 → 4, 14 = 18

# …oder von einem Spielmodus deuten lassen, ohne den eingestellten zu ändern
pool = requests.get(".../api/v1/roll?mode=pool").json()
print(pool["reading"]["headline"])               # 3 successes
```

Ein Würfel, der nicht gelesen werden konnte, hat `"value": 0` und erscheint als `?`. Niemals
mitrechnen.

## Dokumentation

| | |
|---|---|
| [docs/CONCEPT.md](docs/CONCEPT.md) | Was daraus werden soll und warum es so gebaut ist |
| [docs/HARDWARE.md](docs/HARDWARE.md) | Welcher Pi, welche Kamera, wohin montieren, wie beleuchten |
| [docs/API.md](docs/API.md) | Der Vertrag, auf den andere Projekte sich verlassen |
| [docs/TRAINING.md](docs/TRAINING.md) | Ihm die eigenen Würfel beibringen |
| [docs/ANTI-CHEAT.md](docs/ANTI-CHEAT.md) | Was die Fair-Play-Überwachung erkennt — und was nicht |
| [docs/PLAYING.md](docs/PLAYING.md) | Spielbildschirm, Züge, Chips und die beiden Taster |
| [docs/GAME-MODES.md](docs/GAME-MODES.md) | Die Modi, was jeder wertet, und wie ein weiterer dazukommt |
| [docs/DISPLAYS.md](docs/DISPLAYS.md) | Display, Lampen und Summer — Panels, Pins, Verdrahtung |

## Befehle

```bash
dicecore serve                  # API und Einrichtungsseite
dicecore roll                   # einmal lesen, Ergebnis ausgeben
dicecore doctor                 # was diese Maschine kann und was die Kamera meldet
dicecore synth [ordner]         # synthetische Würfe für den Simulator
dicecore sets                   # Datensätze und ob sie trainierbar sind
dicecore train <set>            # ein Modell trainieren (braucht PyTorch)
dicecore camera-module list     # CSI-Module; `camera-module imx519` schreibt die config.txt
```

## Entwicklung

```bash
.venv/bin/pytest                # die ganze Suite, ohne Hardware
.venv/bin/ruff check src tests
```

Die Suite zeichnet ihre Würfel selbst, damit die Erkennung wirklich getestet wird und nicht
nur importiert. Vor Änderungen [CLAUDE.md](CLAUDE.md) lesen.

## TODO

- [ ] An einem echten Turm mit echter Kamera betreiben, [docs/HARDWARE.md](docs/HARDWARE.md) korrigieren
- [ ] Den ersten echten Datensatz sammeln und das erste Modell trainieren
- [ ] Auswahl der oberen Fläche und 6/9-Unterscheidung an echten W20 überprüfen
- [ ] Überlappende und verkantete Würfel erkennen und melden statt falsch lesen
- [ ] Fair-Play-Schwellen (`hand_area_frac`, `motion_threshold`) an echten Händen prüfen
- [ ] Ein echtes ST7789 und ein echtes SSD1306 an einem echten Pi; Treiber geschrieben, ungetestet
- [ ] Ein Discord-Bot als Referenz, in eigenem Repo, der diese API benutzt
- [ ] Provisionierung: Installer, systemd-Unit und die IMX519-Tuning-Datei ausliefern

## Lizenz

CC BY-NC-ND 4.0 mit zusätzlicher Nicht-Militär-Klausel — siehe [LICENSE](LICENSE).
