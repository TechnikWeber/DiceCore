[English](PLAYING.md) · **Deutsch**

# Spielen

Zwei Eingangstüren, ein Dienst.

| | |
|---|---|
| **`/`** | Der **Spielbildschirm**. Der gehört auf den Fernseher am Tisch. |
| **`/setup`** | Alles andere — Kamera, Erkennung, Fair Play, Panel, Training. |

Der Spielbildschirm liegt auf der Wurzel und die Einrichtungsseite nicht, und das mit Absicht:
die Seite, auf die man den ganzen Abend schaut, sollte nicht einen Tab weit hinter sechs
liegen, die man nie anfasst.

## Vier Bildschirme, immer einer

```
Lobby ──► Assistent ──► Spiel ──► Ergebnis
  ▲                                  │
  └──────────────────────────────────┘
```

**Von der Landefläche wird nichts gelesen, bevor ein Spiel läuft.** Die erste Fassung dieses
Bildschirms öffnete direkt in den Modus, der gerade eingestellt war, und begann aufzunehmen —
ein Spieler sah also Zahlen wechseln und hatte keine Ahnung, was vor sich ging. Ein Spiel ist
jetzt etwas, das man *startet*, und die Kamera ruht, bis man das tut.

### Die Lobby

Jeder Modus als Kachel, in drei Gruppen: **Games** (Züge, Spieler, eine Wertung), **Just show
the numbers** (DiceCore liest und meldet, nichts zu spielen) und **Tools** (der Fairness-Test
und das Selbstgebaute). Eine antippen.

Ganz oben stehen zwei Zeilen: der Schalter **echte oder simulierte Würfel** und das Angebot,
**online** gegen andere DiceCores zu spielen. Beide unten in eigenen Abschnitten.

### Der Einrichtungsassistent

Alles per Tippen, denn ein Tisch hat keine Tastatur:

- **Wie viele spielen** — 1 bis 6, und **2 ist schon ausgewählt**.
- **Wer** — *Player 1*, *Player 2* … schon eingetragen, jeder mit eigener Farbe. Auf eine
  Farbe tippen tauscht sie gegen eine, die niemand sonst hat; auf einen Namen tippen benennt
  ihn um, wenn dir danach ist. Nötig ist beides nicht.
- **Die Einstellungen des Spiels selbst**, und nur die, die ein Tisch wirklich entscheidet:
  Chips für Kniffel, Zielpunktzahl und Einstiegsschwelle für Farkle, die Erfolgsschwelle für
  einen Pool. Jede ist eine Reihe Knöpfe mit einer sinnvollen, schon gewählten Antwort.

Start funktioniert beim ersten Tippen. Der Assistent merkt sich Namen und Farben des letzten
Spiels dieser Art, der zweite Abend ist also ein Tippen kürzer als der erste.

### Das Spiel und das Ergebnis

Farben ziehen sich durch alles — die Zugmarke, die Spalten des Zettels, das Protokoll —,
niemand muss sich also merken, welcher Spieler er ist. Wenn die letzte Zeile gebucht ist oder
jemand das Ziel überschreitet, zeigt der Ergebnisbildschirm den Stand und bietet **Play
again** mit denselben Spielern an, oder ein anderes Spiel.

![Die Lobby: jeder Modus als Kachel, gruppiert in Spiele, reine Anzeigen und Werkzeuge](screenshots/lobby.jpg)

![Der Einrichtungsassistent für Kniffel: wie viele spielen als Knopfreihe mit vorgewählter Zwei, dann die Spieler mit ihren Farben, dann Chips pro Spieler](screenshots/wizard.jpg)

![Der Spielbildschirm während eines Kniffel-Zuges: die Kombination in großen Buchstaben, die fünf Würfel als Augen gezeichnet, der Wurfzähler mit zwei verbleibenden Chips und rechts der Spielblock](screenshots/play.jpg)

## Was er zeigt

- **Die Überschrift**, so wie der Modus sie gelesen hat: `18`, `Full house`, `3 successes`.
- **Die Würfel**, gezeichnet — ein Sechsseiter als Augen, alles andere als seine Zahl. Einen
  antippen hält ihn, in einem Spiel, in dem Halten zu den Regeln gehört.
- **Der Wurfzähler**: gefüllte Punkte für verbrauchte Würfe, hohle für übrige, bernsteinfarben
  für Chips. Daneben `throw 2 of 3` in Worten.
- **Der Spielblock**, bei den Spielen, die einen haben. Die offenen Zeilen des aktuellen
  Spielers zeigen, was sie gerade jetzt einbringen würden; eine antippen bucht sie.
- **Die letzten Züge**, an der Seite.

## Züge

Die meisten Spiele sind ein Wurf und fertig. Kniffel und Farkle nicht: ein Zug ist dort drei
Würfe, wobei man dazwischen behält, was man mag, und der Zug endet, wenn man etwas bucht.

**Gehaltene Würfel werden beobachtet, nicht erzwungen.** DiceCore merkt, welche Würfel sich
zwischen zwei Würfen nicht bewegt haben, und zeigt die als behalten — das ist das einzige
Signal, das eine Kamera hat. Rät sie falsch, tipp den Würfel an. Nichts hängt davon ab, dass
die Vermutung stimmt: gewertet wird schlicht, was auf der Fläche liegt, ein falsch erkanntes
Halten kostet dich also nichts als für einen Moment ein falsches Etikett.

**Behaltene Würfel werden auf dem Bildschirm abseits abgelegt**, in einem eigenen
eingezäunten Bereich neben dem Wurf — so, wie man die, die man behält, an den Tischrand
schiebt. Einen antippen legt ihn zurück auf den Haufen. Vorher waren sie an Ort und Stelle
markiert, was dieselbe Information ist und schwerer zu lesen: ein Wurf mischt den Haufen
durch, „welche behalte ich" hieß also jedes Mal, fünf Würfel neu anzusehen.

**Ein neuer Zug nimmt alles wieder auf.** Holds gehören zu dem Zug, in dem sie gemacht
wurden — der erste Wurf einer Runde ist also immer alle Würfel, so wie wenn man sie vom Tisch
zusammenkratzt.

Ein Wurf zählt nur, wenn die Würfel sich wirklich geändert haben. Dieselben ruhenden Würfel
noch einmal anzuschauen — was die Kamera mehrmals pro Sekunde tut — ist kein Wurf und
verbraucht keinen.

### Chips

Ein Chip kauft einen weiteren Wurf, wenn die gewöhnlichen aufgebraucht sind. Wie viele jeder
Spieler bekommt, stellst du im Assistenten oder unter **Detection → Game mode** ein — bis
vier, standardmäßig null.

Chips sind eine **Hausregel**: das Kniffel aus der Schachtel sind drei Würfe pro Zug und sonst
nichts. Viele Tische spielen mit einer Handvoll Marken für einen vierten Wurf, und genau dafür
ist das da; vier ist die Grenze, weil das das Meiste ist, was irgendwer auszuteilen scheint.

**Chips gelten pro Spiel, nicht pro Zug.** Drei Chips heißt drei für den ganzen Abend, einen
auszugeben ist also eine Entscheidung — sie jeden Zug aufzufüllen nähme die Entscheidung weg
und ließe nur den Knopf übrig. Ein neues Spiel gibt sie zurück.

Ein Chip **kann nicht ausgegeben werden, solange gewöhnliche Würfe übrig sind**. Einen durch
einen Fehlgriff auszugeben ist genau die Art Fehler, die ein Spiel nicht zulassen sollte. In
einem Spiel ganz ohne Wurfgrenze, etwa Farkle, kauft ein Chip nichts und sagt das auch.

## Einen Neustart überleben

Ein laufendes Spiel wird nach jedem Zug in `game.json` im Zustandsverzeichnis geschrieben und
beim Start des Dienstes zurückgelesen. Ein Kniffel-Abend ist eine Stunde von jemandes Leben,
und ein Pi, dem der Strom ausgeht, sollte sie nicht kosten. Eine Datei, die nicht gelesen
werden kann, bedeutet ein verlorenes Spiel — nie einen Dienst, der nicht startet.

## Die zwei Taster

Der Browser ist nicht immer dort, wo die Hände sind. Zwei optionale GPIO-Taster tun dieselben
zwei Dinge:

| Taster | Standard-Pin (BCM) | Tut |
|---|---|---|
| Chip | *(aus)* | Einen Chip ausgeben — ein Wurf mehr |
| Zug beenden | *(aus)* | In der Lobby: das eingestellte Spiel starten. Im Spiel: den Zug beenden |

**Einen Zug zu beenden bedeutet nur dort etwas, wo „fertig" die ganze Geschichte ist** —
Backgammon, Mäxchen und alles andere, wo man seine eigenen Figuren zieht und DiceCore nichts
aufzuschreiben hat. Auf einem Spielblock gibt es immer noch etwas zu sagen (*welche Zeile*),
also verweigert der Knopf dort und sagt, worauf er wartet. Früher beendete er den Zug
trotzdem, was den Spieler seinen Wurf kostete: das Schlimmste, was ein echter Knopf tun kann.

In der Lobby startet er das eingestellte Spiel, und das ist der tastaturfreie Weg vom
Aufstehen zum Werfen: einen Knopf drücken, spielen.

Jeden zwischen Pin und Masse verdrahten und **Buttons use the internal pull-up** anlassen; das
ist die ganze Schaltung. Die Pins stellst du unter **Setup → Screen & lamps** ein, `-1` für
einen Taster, den du nicht willst. Sie rufen genau dieselben Endpunkte auf wie die Knöpfe im
Browser, ein Tisch kann also das eine, beides oder nichts benutzen.

## Das Panel während eines Zuges

Der kleine Bildschirm über dem Turm trägt den Zug ebenfalls: `2/3` in der Ecke, ein Punkt je
Chip, und eine Beschriftung, die sich mit dem ändert, was du als Nächstes darfst —

| | |
|---|---|
| **THROW AGAIN** | Würfe übrig |
| **CHIP OR BOOK** | Würfe weg, Chips in der Hand |
| **TURN OVER** | nichts mehr zu tun außer buchen |

Die grüne Lampe bedeutet dasselbe wie immer: du bist mit Werfen dran.

## Die Spielblöcke

Zwei Spiele haben einen eigenen Block, und sie sind absichtlich gegensätzlich geformt — das
ist es, was zeigt, dass die Zugmaschine eine Maschine ist und kein kniffelförmiges Loch.

### Kniffel und Kniffel Extreme

Drei Würfe, dazwischen behaltene Würfel, dann eine Zeile. Jede offene Zeile zeigt, was sie
gerade jetzt einbringen würde; eine antippen bucht sie und reicht den Turm weiter. Eine Zeile
für nichts zu streichen ist ein echter Zug und muss bestätigt werden.

**Kniffel Extreme** ist dieselbe Form mit sechs Würfeln und einem längeren Block:
Fünfer- und Sechserpasch, zwei Paare und drei Paare, ein großes Full House aus drei und drei,
und eine Straße, die von eins bis sechs durchläuft. Der obere Bonus verlangt 84 statt 63 — bei
sechs Würfeln erwartet man in einem Wurf jede Fläche einmal, drei von einer sind also nicht
mehr die Anstrengung, die der Standardbonus belohnt — und zahlt 50.

> Der erweiterte Block ist ein **festgelegter Hausblock, keine Abschrift eines Kaufprodukts**.
> Wenn die Fassung an deinem Tisch etwas anderes sagt: die Zahlen sind eine Tabelle in
> `src/dicecore/play/kniffel.py`, und sie zu ändern ist eine Einzeiler-Aufgabe.

| | Kniffel | Kniffel Extreme |
|---|---|---|
| Würfel | 5 | 6 |
| Zeilen | 13 | 18 |
| Bonus | 35 bei 63 | 50 bei 84 |
| Beste Zeile | Kniffel, 50 | Sechserpasch, 100 |

### Farkle

Das Gegenteil einer festen Wurfzahl: du wirfst, so oft du dich traust. Leg die Würfel
beiseite, die punkten — sie verlassen die Fläche, im nächsten Wurf sind also wirklich weniger
Würfel, was die Kamera direkt sieht —, dann zahl ein, was der Zug eingebracht hat, oder wirf
noch einmal.

Ein Wurf, in dem nichts punktet, ist ein **Farkle**, und der ganze Zug ist verloren. Leg alle
sechs beiseite, und die Würfel sind *heiß*: die ganze Hand kommt zurück und es geht weiter.

Jeder Würfel, den du beiseitelegst, muss punkten. Eine Auswahl mit einem toten Würfel darin
wird abgelehnt statt gewertet, denn ihn mitzuschleppen würde dich stillschweigend die Würfel
eines ganzen Wurfs kosten.

Die umgesetzten Hausregeln: eine einzelne 1 ist 100 und eine einzelne 5 ist 50; ein Drilling
ist 100× die Fläche, außer drei Einsen mit 1000; Vierling, Fünfling und Sechsling verdoppeln,
vervierfachen und verachtfachen das; eine Straße oder drei Paare sind 1500; du brauchst 500 in
einem Zug, um auf das Brett zu kommen; wer zuerst 10 000 hat, gewinnt. Zielpunktzahl und
Einstiegsschwelle sind Einstellungen.

## Mit Leuten spielen, die nicht im Zimmer sind

**Setup → Camera → Live view** bietet die Fläche unter `/api/v1/stream.mjpg` an, und der
Spielbildschirm bekommt einen **Camera**-Knopf, der sie in der Ecke zeigt. Die Mitspieler
können die Würfel fallen sehen, und das ist das Einzige, was aus der Ferne überhaupt
überzeugt.

Zwei Eigenschaften sind zu wissen. Es **öffnet die Kamera nie ein zweites Mal**: geschickt
wird, was die Erkennung zuletzt aufgenommen hat, es läuft während eines Spiels also im Takt
des Lesens und kann nicht mit dem Lesen um das Gerät konkurrieren. Und es ist **aus, bis du es
einschaltest** — ein durchgehendes Bild von allem, was die Kamera sieht, ist etwas anderes als
das einzelne Standbild, um das die Einrichtungsseite bittet, und das ist die Entscheidung des
Zimmers, keine Voreinstellung.

Für sich genommen ist es kein Beweis; was belegbar ist und was nicht, steht in
[ANTI-CHEAT.de.md](ANTI-CHEAT.de.md). Aber eine Zahl, die auf einem Bildschirm erscheint,
während alle die Würfel fallen sehen, ist ungefähr so überzeugend, wie Würfel werden.

## Ohne Würfel spielen

**Der Schalter oben in der Lobby**, neben dem für online: *Real* oder *Simulated*. Mehr ist es
nicht. Simuliert ist die Voreinstellung, weil das die eine Einstellung ist, die auf einer
Kiste funktioniert, an der nichts steckt — ein erstes Spiel sollte keinen Turm brauchen, keine
Kamera und keinen Umweg durch die Einstellungen.

Simulierte Würfel werden von DiceCore gezeichnet und durch die echte Erkennung zurückgelesen,
alles Dahinterliegende verhält sich also genau wie mit Kamera — auch das Behalten: ein
gehaltener Würfel wird nicht neu geworfen und bewegt sich nicht, genau wie er es auf einer
echten Fläche nicht täte. Ein `Throw`-Knopf erscheint dort, wo sonst die Fläche wäre. Auf *Real* zu schalten geht zurück zu der Kamera, die diese
Kiste vorher hatte; hatte sie nie eine, nimmt sie die, die sie wahrscheinlich hat (der
Flachbandanschluss auf einem Pi, USB sonst) und sagt klar Bescheid, wenn die nicht aufgeht.

Dieselbe Wahl steht weiterhin unter **Setup → Camera**, wo die anderen vier Quellen wohnen.
Der Schalter ist dort, weil niemand in den Einstellungen nach „ich habe noch keinen
Würfelturm, kann ich trotzdem spielen" sucht.

## Gegen andere DiceCores spielen

`Play online` in der Lobby: einer von euch macht einen Tisch auf, der Rest tritt mit der
angezeigten Adresse bei, und jeder Spieler würfelt auf seinem eigenen DiceCore, während alle
live zusehen. Die vollständige Anleitung, samt Tailscale, in [ONLINE.de.md](ONLINE.de.md).

## Mehrere Spieler

Im Assistenten gewählt, und das ist der einzige Ort, an dem sie gewählt werden müssen. Der
Turm wandert von selbst weiter: eine Zeile zu buchen beendet den Zug, und der nächste Name
kommt. Die Spieler zu ändern startet ein neues Spiel, denn den Zettel von Spieler drei einem
anderen Spieler drei zu geben wäre schlimmer, als die Punkte zu verlieren.

Ein Spieler ist ein Einzelspiel, und das ist die richtige Form zum Üben, für einen
Fairness-Test oder für eine Maschine, die einfach Zahlen anzeigt. Die Namen lassen sich auch
unter **Setup → Players and turns** setzen, wenn du sie lieber einmal tippst und vergisst.

## Lieber ein eigener Bildschirm

Alles, was der Spielbildschirm tut, ist `/api/v1/game` plus fünf POSTs, alle Teil der
versionierten API — denn ein Spielbildschirm ist genau die Art Sache, von der jemand seine
eigene Fassung schreiben will, auf einem Tablet, auf einem Fernseher, in einer Sprache, die
dieses Projekt nicht benutzt.

```bash
curl -X POST .../api/v1/game/start \
     -d '{"mode": "yahtzee", "players": ["Ada", "Bob"], "params": {"chips": 2}}'
curl http://dicecore.local:8099/api/v1/game            # Zug, Zettel, Optionen, Protokoll
curl -X POST .../api/v1/game/chip                      # ein Wurf mehr
curl -X POST .../api/v1/game/hold  -d '{"index": 2}'   # ein Halten korrigieren
curl -X POST .../api/v1/game/book  -d '{"category": "full_house"}'
curl -X POST .../api/v1/game/next                      # den Zug beenden
curl -X POST .../api/v1/game/reset -d '{"players": ["A", "B"]}'
curl -X POST .../api/v1/game/stop                      # zurück in die Lobby; Lesen hört auf
curl -X POST .../api/v1/throw                          # nur mit Sim-Quelle: würfeln und lesen
```

Über Instanzen hinweg zu spielen sind dieselben fünf POSTs hinter zwei weiteren:

```bash
curl -X POST .../api/v1/table/host -d '{"name": "Ada"}'
curl -X POST .../api/v1/table/join -d '{"address": "pi.local:8099", "name": "Bob"}'
curl -X POST .../api/v1/table/act  -d '{"action": "book", "category": "chance"}'
curl http://dicecore.local:8099/api/v1/table           # Plätze, und welcher deiner ist
```

Der WebSocket unter `/api/v1/events` trägt denselben Spielstand neben jedem Wurf, ein
Bildschirm muss also nie abfragen.

## Lesen, ohne zu spielen

Nichts davon ist Pflicht. Ein Verbraucher, der nur Zahlen will, benutzt weiter `/api/v1/roll`
und ignoriert das Spiel vollständig — und kann mit `?mode=` sogar einen anderen Modus
verlangen, was an dem Spiel, das am Tisch läuft, nichts ändert. Der D&D-Bot und die
Anzeigetafel am Tisch können auf dieselbe Fläche schauen, sich über deren Bedeutung uneinig
sein und beide recht haben.
