[English](CONCEPT.md) · **Deutsch**

# DiceCore — Konzept

Die Referenz dafür, *was das werden soll*. Lies das, bevor du Funktionen hinzufügst; wenn eine
Änderung etwas hier widerspricht, ändere dieses Dokument im selben Commit.

## Ziel

Eine Kamera schaut von oben auf die Landefläche eines Würfelturms (oder auf irgendeine Fläche
oder einen blanken Tisch). DiceCore macht aus dem, was dort landet, **strukturierte Daten**:
wie viele Würfel, welcher Art, mit welchem Wert, und was sie zusammen ergeben. Diese Daten
gibt es als Zahl auf einem Bildschirm, als HTTP/JSON-API, als WebSocket-Ereignisstrom und —
später — direkt in einem Discord-Bot oder einem Spiel.

DiceCore ist die **Engine, die andere Projekte einbinden**, keine Anwendung. Alles, was ein
Verbraucher braucht, ist einen HTTP-Aufruf oder einen Python-Import entfernt, und die
Bildverarbeitung im Inneren bleibt austauschbar.

Drei Eigenschaften entscheiden hier jede Entwurfsfrage:

1. **Simulator zuerst.** Das ganze System läuft auf einem Laptop, mit einem Ordner JPEGs und
   ganz ohne Kamera. Hardwarepfade sind nur auf dem Pi prüfbar, alles andere muss also ohne
   einen prüfbar sein.
2. **Der Pi darf schwach sein.** Ein Pi Zero (v1) ist ARMv6 — kein PyTorch, kein onnxruntime,
   keine modernen OpenCV-Pakete. Aufnahme und Erkennung müssen also **trennbar** sein: der Pi
   holt Bilder, etwas anderes darf denken. Siehe *Installationsformen*.
3. **Der Benutzer entscheidet, wie schlau es wird.** Klassische Bildverarbeitung und ein
   trainiertes Modell sind zwei austauschbare Engines hinter einer Schnittstelle, in der
   Oberfläche wählbar — keine Wanderung von der einen zur anderen.

## Was daran schwer ist

Augen auf einem d6 auf sauberer Fläche zu zählen ist eine gelöste Übung. Die echten Probleme
sind:

- **Polyeder zeigen mehr als eine Zahl.** Bei einem d20 sieht die Kamera die obere Fläche
  *und* die umliegenden schräg dazu. „Die größte, mittigste, frontalste Ziffer" zu lesen ist
  die eigentliche Aufgabe — nicht OCR über alles Sichtbare.
- **Ziffern sind mehrdeutig.** 6 gegen 9 braucht die Unterstrich-Konvention (oder die
  Ausrichtung des Würfels); 1 gegen 7 unterscheidet sich je nach Hersteller.
- **Würfel unterscheiden sich stark.** Farbe, Durchsichtigkeit, metallisch, marmoriert,
  bedruckt gegen roh. Ein auf einen Satz trainiertes Modell überträgt sich schlecht auf einen
  anderen — und genau deshalb muss der Trainingsablauf so einfach sein, dass Nachtrainieren
  für einen neuen Satz eine Fünf-Minuten-Sache ist und kein Projekt.
- **Der Turm bewegt sich und das Licht ändert sich.** Feste Geometrie darf man nicht ewig
  annehmen; der Flächenbereich und der Maßstab (mm pro Pixel) sind Konfiguration, keine
  Konstanten.
- **Wissen, wann der Wurf vorbei ist.** Ein mitten im Rollen gegriffenes Bild ist wertlos.
  Die Ruhe-Erkennung (Bilddifferenzen, bis die Bewegung aufhört, dann N stabile Bilder) ist
  Teil der Kette, kein Nachgedanke.
- **Wissen, dass die Zahl noch stimmt.** Die Würfel zu lesen ist nur die Hälfte: zwischen
  Kamera und Spiel kann eine Hand einen Würfel umdrehen. Die Fläche danach zu beobachten ist
  aus demselben Grund Teil der Kette wie die Ruhe-Erkennung — siehe *Fair Play*.

## Architektur

```
        ┌──────────────┐   Bilder    ┌──────────────┐   RollResult   ┌────────────┐
        │   Capture    │ ──────────► │    Engine    │ ─────────────► │  Ausgaben  │
        │              │             │              │                │            │
        │ picamera2    │             │ classic      │                │ HTTP/JSON  │
        │ rpicam-still │             │ model (onnx) │                │ WebSocket  │
        │ v4l2/OpenCV  │             │ remote       │                │ Web-UI     │
        │ sim / folder │             │              │                │ Discord…   │
        └──────────────┘             └──────────────┘                └────────────┘
                │                            ▲
                │        ┌──────────────┐    │
                └──────► │   Dataset    │────┘  etikettierte Bilder → Training → Modell
                         └──────────────┘
```

Jeder Pfeil ist eine schlichte Python-Schnittstelle mit einer simulierten Umsetzung, und jeder
Kasten ist allein über Konfiguration austauschbar.

### Aufnahme

`FrameSource.grab() -> Frame`. Umsetzungen: `picamera2` (Pi, CSI), `rpicam` (ruft
`rpicam-still` auf, der Ausweg für Pis, auf denen picamera2 mühsam ist), `v4l2`
(USB-Kameras über OpenCV), `sim` (gezeichnete Würfel — die Voreinstellung), `folder` (ein
Verzeichnis Bilder, abgespielt), `push` (Bilder, die über die API von einem anderen
DiceCore-Knoten ankommen).

**CSI-Kameramodule sind Konfiguration, kein Glück.** Ein Pi bindet nur einen Sensor, den die
Firmware kennt: die vier offiziellen Module findet `camera_auto_detect=1`, alles andere —
Arducam IMX519 16MP, 64MP Hawkeye, OV64A40 Owlsight, Pivariety — braucht
`camera_auto_detect=0` plus ein ausdrückliches `dtoverlay=` in `/boot/firmware/config.txt` und
einen Neustart. Dieses Modul auszuwählen gehört in die Weboberfläche, nie in eine SSH-Sitzung.
Die Logik ist aus YonderRC portiert (`packages/vehicle/src/system/bootConfig.ts`),
einschließlich der teuer erkauften Einzelheit, dass Raspberry Pis eigene Tuning-Datei
`imx519.json` keinen Autofokus-Algorithmus enthält — der IMX519 braucht also die mitgelieferte
`imx519-af.json`, oder sein Objektiv bewegt sich schlicht nie.

### Engine

`Engine.read(frame) -> RollResult`. Drei Umsetzungen:

- **`classic`** — kein Training, keine Abhängigkeiten außer OpenCV. Trennt Würfel von der
  Fläche, zählt Augen pro Würfel per Blob-Erkennung. Ehrlicher Geltungsbereich: Würfel mit
  Augen (d6 und Augen-d10-Flächen), gutes Licht, kontrastierende Fläche. Das macht das Projekt
  am ersten Tag nützlich, und es bleibt nützlich als Rückfall, wenn kein Modell geladen ist.
- **`model`** — ein trainiertes Netz. Absichtlich zwei Stufen: **(a)** die Würfel finden
  (Segmentierung oder ein kleiner Detektor), **(b)** jeden ausgeschnittenen Würfel in
  `(Würfelart, Wert)` einordnen. Zwei Stufen statt eines Ende-zu-Ende-Detektors, weil
  Ausschnitte billig zu etikettieren sind, der Klassifikator klein genug für einen Pi 4/5 ist
  und ein neuer Würfelsatz nur ein Nachtrainieren von Stufe (b) bedeutet.
- **`remote`** — leitet das Bild an `/api/v1/detect` einer anderen DiceCore-Instanz weiter und
  gibt deren Antwort zurück. Das macht einen ARMv6-Zero nützlich: der Pi nimmt auf, ein PC
  oder ein Pi 5 liest. Die API ist so oder so identisch, ein Verbraucher merkt den Unterschied
  also nie.

### Fair Play

Die Fläche hört nicht in dem Moment auf zu zählen, in dem sie gelesen wurde. Für `hold_s`
danach bleibt sie beobachtet, und am Ende werden die Würfel noch einmal gelesen und mit dem
verglichen, was veröffentlicht wurde. Eine hineingreifende Hand ist *verdächtig*; eine
**veränderte Lesung** ist disqualifizierend. Diese Trennung ist der ganze Entwurf: wer am Turm
vorbei nach seinem Getränk greift, darf keinen rechtmäßigen Wurf verlieren, und ein zwischen
zwei Bildern umgedrehter Würfel darf nicht durchrutschen.

Die Regeln liegen in `integrity.py` und werden auf Zahlen entschieden, nicht auf Pixeln — was
als Schummeln gilt, ist also testbar. `guard.py` macht nur Bilder zu Ereignissen.

**Es ist Manipulationserkennung, keine Manipulationssicherheit**, und DiceCore behauptet nie,
ein Wurf sei fair gewesen — es sagt, was passiert ist, und lässt den Verbraucher entscheiden.
Wer die Kamera beherrscht, hebelt es aus, und genau deshalb sind ein eingefrorenes Bild und
ein abgedecktes Objektiv selbst Fehler statt Schweigen. [docs/ANTI-CHEAT.de.md](ANTI-CHEAT.de.md)
nennt die Grenzen vollständig; sie gehören in die Dokumentation und nicht in eine Fußnote,
denn eine Fairness-Funktion, die zu viel verspricht, ist schlimmer als keine.

### Installationsformen

| Form | Aufnahme | Engine | Wofür |
|---|---|---|---|
| **Alles in einem** | Pi 4 / Pi 5 | `classic` oder `model` lokal | Der Normalfall |
| **Geteilt** | Pi Zero / Pi 3 | `remote` → PC oder Pi 5 | Schwacher Pi, oder ein großes Modell |
| **Nur Agent** | Pi Zero | keine — schickt Bilder | Das absolute Minimum auf dem Pi |
| **Schreibtisch** | `sim` / `folder` | beliebig | Entwicklung, Training, Tests |

### Datensatz und Training

Die Trainingsdaten kommen aus dem Ding selbst: **du würfelst, DiceCore rät, du bestätigst oder
korrigierst.** Jeder bestätigte Wurf ist ein etikettiertes Beispiel. Diese Schleife lebt
vollständig in der Weboberfläche — keine Kommandozeile, kein Etikettierwerkzeug von Hand, kein
Ordnerjonglieren:

1. Einen **Satz** wählen oder anlegen („meine schwarzen d20", „der durchscheinende Café-Satz").
2. Würfeln. Das Bild wird aufgenommen, die Würfel werden lokalisiert, jeder bekommt eine
   Vermutung.
3. Auf einen falschen Wert tippen, den richtigen eingeben. Bestätigen.
4. Jederzeit: **Train**. Fortschritt, Loss und Genauigkeit laufen live in die Seite; das
   Ergebnis ist eine ONNX-Datei, die die `model`-Engine aufgreift.

Die Ablage ist absichtlich langweilig: ein Verzeichnis pro Sitzung, die Originalbilder als
JPEG neben je einem JSON pro Bild mit den Würfelkästchen, -arten und -werten sowie den Kamera-
und Lichtangaben. Kopierbar, einsehbar und von jedem anderen Werkzeug lesbar.

Das Training selbst braucht PyTorch, läuft also dort, wo PyTorch läuft — auf dem PC. Ein Pi,
der nicht trainieren kann, kann trotzdem *sammeln* (der Datensatz bleibt auf dem Pi oder wird
zum Trainer geschickt) und kann das exportierte Modell *ausführen*, wenn er ein Pi 4/5 ist.
Die Oberfläche sagt klar, was diese Maschine davon kann, statt auf halber Strecke zu
scheitern.

### Spielmodi

Die Würfel zu lesen und das *Ergebnis* zu lesen sind zwei Aufgaben. Ein Modus sagt, welche
Würfel vorkommen dürfen, wie aus den Flächen eine Antwort wird und was in großen Buchstaben
auf einen Bildschirm gehört — als Tabelleneintrag plus reine Funktion, nie als Änderung an der
Erkennung.

Das ist es, was das Projekt davon abhält, über ein einziges Spiel zu handeln. Der Kamera ist
egal, ob fünf Sechsen dreißig Punkte oder ein Kniffel sind; der Wertung ist egal, wie die
Sechsen erkannt wurden. Ein Modus ist außerdem die billigste Genauigkeitseinstellung, die es
gibt, denn zu nennen, welche Würfel ein Spiel benutzt, verengt, was die Erkennung erwägen
muss.

Ein Modus ist keine Regel-Engine: DiceCore kennt deinen Modifikator nicht, nicht wer dran ist
und nicht, wofür du gewürfelt hast. Siehe [docs/GAME-MODES.de.md](GAME-MODES.de.md).

### Spielen, nicht nur lesen

Manche Spiele sind nicht ein Wurf. Kniffel sind drei, mit Würfeln, die dazwischen liegen
bleiben — es gibt also eine Zugmaschine (`play/turns.py`), einen Spielblock
(`play/kniffel.py`) und ein lebendes Spiel, das Browser und Panel beide zeichnen
(`play/session.py`).

**Gehaltene Würfel werden beobachtet, nicht erzwungen.** Eine Kamera kann keine Hand aufhalten,
und nichts hier hängt davon ab, dass die Vermutung stimmt: gewertet wird, was auf der Fläche
liegt. Die Haltemarkierungen sagen dem Spieler nur, was behalten wird, und der Browser kann
sie korrigieren.

Das Spiel lebt auf dem *Server*, nicht im Browser — damit der Bildschirm über dem Turm
ebenfalls „Wurf 2 von 3" sagen kann, ein geschlossener Tab nichts verliert und ein Handy am
anderen Tischende dasselbe Spiel sieht statt seiner eigenen Kopie.

`/` ist der Spielbildschirm und `/setup` die Werkstatt. Zwei Eingangstüren, ein Dienst; siehe
[docs/PLAYING.de.md](PLAYING.de.md).

### Mehrere DiceCores, ein Spiel

Ein Tisch ist nicht zwingend ein Zimmer. Eine Instanz macht einen Tisch auf, andere treten
über das Netz bei, und ein Spiel läuft Zug für Zug über alle — jeder würfelt auf seiner
eigenen Fläche, mit seiner eigenen Kamera oder seinem eigenen Simulator.

**Der Gastgeber besitzt das Spiel; Gäste besitzen nichts.** Sie spiegeln es und bitten darum.
Nichts wird zusammengeführt und kein Konflikt aufgelöst, denn es gibt genau eine Antwort auf
„wer ist dran" — die Schwierigkeit eines rundenbasierten Spiels, das in drei Zimmern zugleich
läuft. Die Zugregel wird beim Gastgeber durchgesetzt, nie am Knopf. Siehe
[docs/ONLINE.de.md](ONLINE.de.md).

## Ausgaben und Modi

Dasselbe `RollResult` wird über jede Ausgabe ausgeliefert; ein Modus wählt nur, was betont
wird, nie eine andere Kette.

- **Anzeige** — die Zahl, groß, im Browser. Gesamt oder pro Würfel.
- **API** — `GET /api/v1/roll` (jetzt lesen), `GET /api/v1/state` (letztes Ergebnis),
  WebSocket `/api/v1/events` (ein Ergebnis, sobald die Würfel liegen, dann noch einmal mit
  seinem Fair-Play-Urteil).
- **Notation** — eine Zusammenfassung in Würfelnotation für Verbraucher, die Text wollen:
  `2d20+1d6 → 14, 3, 5`.
- **Lesung** — was der aktive Modus daraus gemacht hat: eine Überschrift für einen Bildschirm,
  ein Wert zum Rechnen und die Details des Modus selbst.
- **Verbraucher** — ein Discord-Bot, ein Spiel, eine Anzeigetafel. Sie leben in eigenen Repos
  und hängen an dieser API, nicht an diesem Code. Diese Richtung ist der ganze Punkt.
- **Ausgehend** — derselbe Wurf in die andere Richtung geschoben: ein Discord-Webhook, eine
  Avrae-Benutzervariable, die ein Alias zurückliest, oder JSON an eine beliebige URL. Am Wurf
  ändert sich nichts; nur wer das Gespräch beginnt. Siehe [docs/AVRAE.de.md](AVRAE.de.md).

## Was es nicht wird

- Kein Würfel*generator* — kein Zufallsgenerator, keine Regel-Engine, keine Charakterbögen.
  DiceCore liest echte Würfel, Punkt.
- Kein allgemeines OCR-Projekt.
- Kein Cloud-Dienst. Es läuft in deinem Netz; nichts verlässt es.
- Kein Prüfwerkzeug in Casino-Güte. Es meldet Eingriffe in eine *ruhende* Fläche; über
  gezinkte Würfel oder einen kontrollierten Wurf weiß es nichts. Die zu erkennen ist ein
  Statistikproblem, das ein Verbraucher auf diesen Daten lösen kann.

## Fahrplan

1. **Gerüst** — Konfiguration, Aufnahme (Simulator + Pi), klassische d6-Erkennung, API,
   Weboberfläche, Kameramodulauswahl. *Man kann würfeln und eine Zahl sehen.*
2. **Datensatz + Lernschleife** — Satzverwaltung, Bestätigen/Korrigieren als Etikettierung,
   Trainingslauf mit Live-Fortschritt, ONNX-Export, `model`-Engine. *Man kann ihm seine Würfel
   beibringen.*
3. **Polyeder-Qualität** — Auswahl der oberen Fläche, 6/9-Unterscheidung, gemischte Würfe,
   Ruhe- und Fair-Play-Schwellen an echtem Material eingestellt.
4. **Verbraucher** — ein Referenz-Discord-Bot und eine minimale Spielanbindung, jeweils im
   eigenen Repo, als Beweis, dass die API wirklich einbindbar ist.
