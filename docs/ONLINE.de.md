[English](ONLINE.md) · **Deutsch**

# Gegen ein anderes DiceCore spielen

Jeder hat sein eigenes DiceCore. Eines hält das Spiel, die anderen sitzen daran. Jeder Spieler
würfelt auf **seiner eigenen** Landefläche — seiner eigenen Kamera oder seinem eigenen
Simulator — und was dort liegt, erscheint gleichzeitig auf allen Bildschirmen.

Es gibt nichts zu installieren und nichts anzumelden. Es ist ein Knopf auf dem
Spielbildschirm.

```
   Philipps DiceCore                    Maries DiceCore
   ┌──────────────────┐                 ┌──────────────────┐
   │  hier lebt das   │◄── WebSocket ───│  ein Spiegel     │
   │  Spiel           │───────────────► │  davon           │
   └──────────────────┘                 └──────────────────┘
     seine Kamera/Sim                     ihre Kamera/Sim
```

## Wie es geht

**Einer ist Gastgeber.** Auf dem Spielbildschirm: `Play online` → `Open a table`. Der
Bildschirm zeigt eine Adresse; lies sie vor.

**Alle anderen treten bei.** `Play online`, diese Adresse ins Feld tippen, `Join`. Die
Platzliste füllt sich auf jedem Bildschirm, während die Leute ankommen.

**Der Gastgeber sucht das Spiel aus und startet es.** Die Plätze *sind* die Spieler, in der
Reihenfolge, in der sie sich hingesetzt haben — es gibt also keine Spielerliste auszufüllen,
der Assistent zeigt die Namen, die er schon hat.

**Dann wird gespielt.** Wer dran ist, würfelt auf seinem eigenen DiceCore; alle anderen sehen
die Würfel live fallen. Buchen, Halten, Chips und Einzahlen funktionieren wie an einem
einzigen Tisch, und der Bildschirm sagt schlicht `watching`, wenn du nicht dran bist.

Zum Gehen: `Leave the table` in der Ecke. Das Spiel läuft ohne dich weiter, und dein Platz
bleibt frei — mit demselben Namen wieder beizutreten setzt dich zurück in deine eigene Spalte
auf dem Zettel statt ans Ende des Tisches.

## Was „dasselbe Netzwerk" heißt

Alles, wo eine Maschine eine TCP-Verbindung zu einer anderen aufbauen kann:

| | |
|---|---|
| **Dasselbe WLAN oder LAN** | Der Normalfall. Nimm die Adresse, die der Gastgeber-Bildschirm zeigt. |
| **Tailscale** | Funktioniert direkt. Der Bildschirm zeigt auch die `100.x.y.z`-Adresse — die ist es dann. |
| **Hamachi, ZeroTier, ein VPN** | Dieselbe Idee: die Adresse, die dieses Netz dem Gastgeber gibt. |
| **Über das offene Internet** | Nicht, ohne darüber nachzudenken. Siehe *Wer beitreten kann* unten. |

Der Gastgeber-Bildschirm listet jede Adresse auf, unter der er sich selbst findet. Lies die
vor, die zu dem Netz gehört, das ihr teilt — die `100.x` bei Tailscale, die `192.168.x` im
Heimnetz.

## Sim-Würfel: ganz ohne Würfel spielen

DiceCore braucht keine Kamera, um zu spielen. Der Schalter oben in der Lobby sagt *Real* oder
*Simulated*; tipp auf **Simulated**, und dort, wo sonst die Landefläche wäre, erscheint ein
`Throw`-Knopf. Mehr ist der Unterschied nicht — und es ist die Voreinstellung, eine Kiste
spielt also direkt nach dem Auspacken.

Der Simulator ist kein Zufallsgenerator mit angeklebter Anzeige. Er **zeichnet die Würfel und
liest das Bild durch die echte Erkennung zurück** — dieselbe Segmentierung, dasselbe
Augenzählen, dieselben Spielmodi, dieselben Blöcke, dasselbe Panel. Was auf dem Bildschirm
steht, wurde wirklich *gelesen*, und ein Fehler irgendwo in dieser Kette zeigt sich auf einem
Laptop statt erst auf einem Turm.

Damit funktionieren alle Kombinationen, und keine davon ist ein Sonderfall:

- Alle um einen Bildschirm, ein echter Turm. Der Ursprungsfall.
- Alle um einen Bildschirm, gar kein Turm — Sim-Würfel, `Throw` tippen.
- Vier Leute in vier Zimmern, jeder mit Turm.
- Vier Leute in vier Zimmern, **keiner** mit Turm.
- Zwei mit Turm und zwei ohne, im selben Spiel. Am Zettel sieht man es nicht.

Jede Instanz entscheidet für sich. Der Gastgeber zwingt niemandem eine Quelle auf, denn wessen
Würfel du wirfst, ist deine Sache.

## Wie es funktioniert, und was das kostet

**Eine Instanz besitzt das Spiel.** Die `GameSession` des Gastgebers ist die einzige, die
existiert; alle anderen haben einen Spiegel davon und bitten sie um Dinge. Niemand führt etwas
zusammen und niemand löst einen Konflikt auf, denn es gibt nie mehr als eine Antwort auf „wer
ist dran". Diese Schieflage ist der Entwurf, keine Abkürzung:

- **Ein Gast, der den Tab schließt, verliert nichts.** Das Spiel liegt nicht in seinem
  Browser.
- **Ein Gast, dem das WLAN abreißt, verliert nichts.** Er verbindet sich neu — mit
  wachsendem Abstand — und sein Platz gehört noch ihm.
- **Wenn der Gastgeber weg ist, ist der Abend vorbei.** Der Zettel lag dort. Das ist der
  Handel.

Die Regel, auf der das Ganze ruht, ist: **nur wer dran ist, darf handeln.** Sie wird beim
Gastgeber durchgesetzt, nicht am Knopf — ein Gast mit veraltetem Bildschirm darf keine Zeile
buchen, bloß weil seine Kopie sagte, er sei dran. Er bekommt `It is not your turn.` zurück,
und sein Bildschirm holt auf. `src/dicecore/table/protocol.py` hat das in einer Funktion, und
`tests/test_table.py` nagelt es fest.

Würfe reisen als **Zahlen, nicht als Bilder**. Ein Gast liest seine eigene Fläche mit seiner
eigenen Erkennung und schickt `[{"kind": "d6", "value": 4}, …]` hoch. Damit bleibt ein Zug
unter einem Kilobyte, und ein Pi Zero ohne OpenCV kann an einem Tisch sitzen, solange
irgendetwas seine Bilder liest.

## Wer beitreten kann

**Jeder, der den Port erreicht.** Es gibt kein Passwort, und das ist Absicht — dieselbe
Entscheidung wie im Rest von DiceCore, das für einen Tisch in einem Zimmer gebaut ist und
nicht für das offene Internet. In einem Heimnetz oder einem Tailnet ist das genau richtig: wer
es erreichen kann, ist im Haus.

Leite den Port nicht ins Internet weiter. Was jemand tun könnte, ist deinem Tisch beitreten
und einen Zug machen — ärgerlich, nicht gefährlich. Aber das Live-Kamerabild, falls du es
eingeschaltet hast, ist eine Kamera.

Die Platzliste auf dem Gastgeber-Bildschirm zeigt genau, wer verbunden ist, und das Schließen
des Tisches trennt alle.

## Wenn es nicht geht

**„did not answer"** — die Adresse ist falsch, das andere DiceCore läuft nicht, oder eine
Firewall steht dazwischen. Der Port ist der aus der Adresse; auf einem Pi ist es 8099.

**„That DiceCore speaks table protocol 2, this one speaks 1."** — einer von euch hat eine
ältere Version. `git pull && systemctl restart dicecore` auf der älteren.

**„The table is full (8 seats)."** — acht ist die Grenze. Es ist ein Würfelspiel.

**Ein Platz sagt „lost the connection"** — diese Instanz ist abgefallen. Sie verbindet sich
von selbst neu; das Spiel wartet, wenn sie dran ist.

**Alles wirkt eingefroren** — schau in die Ecke der Kopfzeile. `waiting for Marie` heißt, es
funktioniert und Marie hat nur noch nicht geworfen.
