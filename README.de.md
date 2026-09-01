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
- **Eine Label-Schleife statt eines Label-Werkzeugs.** Würfeln, hinschauen, korrigieren,
  bestätigen — jeder bestätigte Wurf ist ein Trainingsbeispiel, im Browser, ohne Kommandozeile.
- **Training aus dem Browser**, mit laufender Loss- und Genauigkeitsanzeige, am Ende ein
  ONNX-Modell, das die Engine übernimmt. Training braucht PyTorch und läuft deshalb auf dem
  PC; die Oberfläche sagt das offen, statt auf halbem Weg abzubrechen.
- **Eine versionierte API** und ein WebSocket-Stream, gedacht zum Einbinden in andere Projekte.
- **CSI-Kameramodule als Einstellung** — inklusive Arducam IMX519 / 64MP / Owlsight /
  Pivariety, die ein Pi nicht selbst erkennt. Die Auswahl in der Oberfläche schreibt den
  `dtoverlay` in die `config.txt` und sagt, dass neu gestartet werden muss.
- **Alles davon ohne Hardware.** `dicecore synth` zeichnet Würfel, die Quelle `folder` spielt
  sie ab, und alles oben Genannte läuft damit auf dem Laptop.

![Der Reiter „Training“: gespeicherte Würfe, pro Würfel die Schätzung der Engine vorausgefüllt, bereit zum Korrigieren und Bestätigen](docs/screenshots/training.jpg)

## Fünf Minuten, ohne Hardware

```bash
git clone https://github.com/TechnikWeber/DiceCore && cd DiceCore
python3 -m venv .venv && .venv/bin/pip install -e '.[vision,server,dev]'

.venv/bin/dicecore synth --count 20 --kinds d6,d20   # erfundene Würfe zum Lesen
.venv/bin/dicecore serve                             # → http://localhost:8099/
```

Danach `curl localhost:8099/api/v1/roll`:

```json
{"dice": [{"kind": "d6", "value": 3, "confidence": 0.99, "box": {"x": 88, "y": 154, "w": 98, "h": 98}}],
 "total": 3, "count": 1, "notation": "1d6 → 3", "engine": "classic", "warnings": []}
```

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
print(roll["notation"], "=", roll["total"])      # 1d6+1d20 → 4, 14 = 18
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
- [ ] Ein Discord-Bot als Referenz, in eigenem Repo, der diese API benutzt
- [ ] Provisionierung: Installer, systemd-Unit und die IMX519-Tuning-Datei ausliefern

## Lizenz

CC BY-NC-ND 4.0 mit zusätzlicher Nicht-Militär-Klausel — siehe [LICENSE](LICENSE).
