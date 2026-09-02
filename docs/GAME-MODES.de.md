[English](GAME-MODES.md) · **Deutsch**

# Spielmodi

DiceCore liest Würfel. Ein **Modus** liest das *Ergebnis*. Das sind zwei verschiedene
Aufgaben, und sie auseinanderzuhalten ist das, was verhindert, dass hieraus ein Projekt über
ein einziges Spiel wird: der Kamera ist es egal, ob fünf Sechsen dreißig Punkte oder ein
Kniffel sind, und der Wertung ist es egal, wie die Sechsen erkannt wurden.

Ein Modus entscheidet drei Dinge:

1. **Welche Würfel vorkommen dürfen.** Das einzuschränken ist der billigste Genauigkeitsgewinn
   überhaupt, und es erlaubt DiceCore zu sagen *„das sind zwei Würfel und es liegen drei auf
   der Fläche"*, statt den übrig gebliebenen vom letzten Wurf stillschweigend mitzuzählen.
2. **Wie aus den Flächen eine Antwort wird.** Eine Summe, eine Zahl von Erfolgen, eine
   Kombination, ein Vergleich mit einem Zielwert.
3. **Was in großen Buchstaben auf dem Bildschirm steht.** `18`, `3 successes`, `Full house`,
   `Mäxchen!`

Modi liegen in [`src/dicecore/modes/catalogue.py`](../src/dicecore/modes/catalogue.py) als
Tabelle und in [`scoring.py`](../src/dicecore/modes/scoring.py) als reine Funktionen. Ein
Spiel hinzuzufügen ist ein Eintrag plus eine Funktion — keine Änderung an der Erkennung, der
API oder der Weboberfläche, die ihr Einstellungsformular aus den Parametern des Modus selbst
baut.

## Die Liste

| Modus | Würfel | Was er tut |
|---|---|---|
| **Normal** | 1–6 × d6 | Augen, addiert. Fast jedes Brettspiel, das es gibt. |
| **Normal, erweitert** | 1–6 × d6, d10 | Sechs- und Zehnseiter zusammen. Die Null eines d10 zählt zehn. |
| **Pen-and-Paper-Rollenspiel** | der Polyeder-Satz | Jeder Würfel gemeldet und addiert; ein d100 und ein d10 zusammen als 1–100 gelesen; eine natürliche 20 oder 1 ausgerufen. |
| **Würfelpool** | beliebig | Zählen, wie viele Würfel den Zielwert erreicht haben. |
| **Bester oder schlechtester von mehreren** | 2–4 | Nur der höchste Würfel zählt — oder der niedrigste. |
| **Explodierende Würfel** | 1–3 | Ein Würfel auf seinem Maximum wird erneut geworfen und addiert. |
| **Unter einen Zielwert würfeln** | 1–3 | Erfolg, wenn der Wurf den Zielwert erreicht oder unterbietet. |
| **Kniffel / Yahtzee** | 5 × d6 | Die Kombination, nicht die Summe. Drei Würfe und ein Zettel. |
| **Kniffel Extreme** | 6 × d6 | Ein längerer Block: Fünfer- und Sechserpasch, zwei und drei Paare, eine 1–6-Straße. |
| **Farkle / Zehntausend** | 1–6 × d6 | So oft werfen, wie du dich traust; beiseitelegen, einzahlen oder alles verlieren. |
| **Backgammon** | 2 × d6 | `5-3`, oder `double 4 — four moves`. |
| **Mäxchen** | 2 × d6 | Zwei Würfel als zweistellige Zahl. 21 ist das Mäxchen. |
| **Ein Würfel, groß** | 1 | Eine einzelne Zahl, so groß der Bildschirm es zulässt. |
| **Fairness-Test** | 1 | Ist dieser Würfel gezinkt? |
| **Selbst gebaut** | beliebig | Regel und Zahlen selbst aussuchen. |

Modus wechseln mit der Auswahl oben in **Roll**; die Zahlen eines Modus anpassen unter
**Detection → Game mode**.

## Die, die eine Erklärung verdienen

### Würfelpool — ein Modus, sehr viele Spiele

Eine Handvoll werfen, zählen, wie viele einen Zielwert erreicht haben. Das ist kein Spiel,
das ist eine Familie:

| Spiel | Würfel | Schwelle | Zehner zählen doppelt |
|---|---|---|---|
| Warhammer 40.000 („trifft ab 4+") | d6 | 4 | nein |
| Shadowrun | d6 | 5 | nein |
| World of Darkness / Vampire | d10 | 8 | **ja** |
| Blades in the Dark | d6 | 4 | nein |

Zwei Einstellungen decken alle ab, und genau deshalb ist das ein Modus und nicht vier.

### Explodierende Würfel

Ein Würfel auf seinem Maximum wird erneut geworfen und die Ergebnisse addieren sich. DiceCore
hält die laufende Summe zwischen den Würfen, und die Anzeige sagt `16…` — mit den Punkten —
solange der Wurf noch offen ist, damit niemand von einem halben Ergebnis weggeht. Sobald ein
Würfel darunter landet, ist die Summe endgültig und der nächste Wurf beginnt bei null.

### Unter einen Zielwert würfeln

Erfolg, wenn der Wurf *auf oder unter* der Zahl liegt. Call of Cthulhu würfelt prozentual: ein
d100 (die Zehner) und ein d10 (die Einer) zusammen als 1–100 gelesen, wobei doppelt null 100
ist — die einzige Stelle im Würfelwesen, an der zwei Nullen das bestmögliche Ergebnis sind.
GURPS nimmt stattdessen drei Sechsseiter; schalt `percentile` aus und es funktioniert genauso.

### Fairness-Test

Wirf denselben Würfel ein paar hundert Mal, und DiceCore zählt mit. Ein
Chi-Quadrat-Anpassungstest gegen eine Gleichverteilung sagt eines von drei Dingen:

- **not enough** — ein d6 braucht etwa 30 Würfe, bevor der Test etwas bedeutet, ein d20 etwa
  100
- **nothing unusual** — die Verteilung gibt keinen Anlass, den Würfel für gezinkt zu halten
- **unusual / very unusual** — dieses Muster taucht bei weniger als einem von zwanzig fairen
  Würfeln auf (oder einem von hundert)

Lies die dritte Antwort sorgfältig. Einer von zwanzig fairen Würfeln landet in „unusual" — das
ist es, was eine 5-%-Schwelle *bedeutet*, kein Skandal. Und es gibt absichtlich kein Urteil
„fair", denn das kann dieser Test nicht zeigen: er kann nur das Gegenteil nicht zeigen.

**Start again** unter *Detection → Game mode* leert die Strichliste — was du willst, sobald du
einen anderen Würfel in die Hand nimmst.

### Selbst gebaut

Jedes Spiel, das nicht in der Liste steht: Regel aussuchen (`sum`, `pool`, `best`, `under`)
und die Zahlen. Wenn du es dauernd benutzt, verdient dieses Spiel einen richtigen Eintrag im
Katalog — schick die Zahlen mit, dann wird einer daraus.

## Welche Würfel bekannt sind

`d2 d3 d4 d6 d8 d10 d100 d12 d20` — die sieben eines Rollenspielsatzes plus die beiden
kleinen, die dabei auftauchen. Ein d3 ist ein echter Würfel, auch wenn die meisten Tische
einen von einem d6 ablesen, und ein d2 taucht für Münzwurf-Effekte auf.

Alles lässt sich *anlernen*: die Etikettenliste bietet die Flächen an, die eine Art hat, ein
d20 sind also zwanzig Klassen und ein d4 vier. Was sich unterscheidet, ist das Würfeln — etwa
zehn bestätigte Beispiele pro Fläche, also sechzig für einen d6 und zweihundert für einen d20.

Es gibt Arten darüber hinaus — d5, d7, d14, d16, d24, d30 aus den Dice-Lab- und
Zocchi-Sätzen — und jede ist eine Zeile in `DIE_FACES` plus eine in `READING`. Füg deine
hinzu, wenn du sie besitzt.

## Zehnseitige Würfel

Ein d10 ist der eine Würfel, dessen Beschriftung nicht einheitlich ist. Moderne zeigen **0–9**
und lassen das Spiel entscheiden, was die Null wert ist; ältere Sätze sind **1–10** bedruckt,
wobei die Zehn ein zweistelliges Zeichen auf einer einzigen Fläche ist.

Das ist eine Eigenschaft *deiner Würfel*, nicht des Spiels, wird also einmal unter
**Detection → Game mode** gesetzt und entscheidet über die Etiketten, auf die ein Modell
trainiert wird — es später zu ändern heißt, neu zu etikettieren.

**Was die Null wert ist, ist eine andere Frage, und die gehört dem Spiel.** In fast jedem
zehn, was unter demselben Feld die allgemeine Antwort ist; manche Hausregeln zählen sie aber
als nichts, damit eine Folge 0-1-2-3-4-5 eine Straße ist. Jeder Modus darf die allgemeine
Antwort mit einer eigenen überschreiben, und *wie allgemein eingestellt* ist die dritte Wahl —
ein Tisch kann also ein Spiel haben, in dem eine Null zehn ist, und eines, in dem sie nichts
ist, ohne dass eines von beiden falsch wäre.

## Aus eigenem Code

```python
import requests

roll = requests.get("http://dicecore.local:8099/api/v1/roll?mode=pool").json()
print(roll["reading"]["headline"])          # "3 successes"
print(roll["reading"]["extras"]["successes"])
```

`?mode=` liest einen Wurf als ein anderes Spiel, **ohne den eingestellten zu ändern** — ein
Bot, der Erfolge zählt, und ein Bildschirm, der eine Summe zeigt, können sich also eine Fläche
teilen. `GET /api/v1/modes` listet alle mit ihren Parametern auf, und daraus sollte die
Modusauswahl eines Verbrauchers gebaut werden.

Jede Lesung hat dieselbe Form:

```json
{"mode": "yahtzee", "headline": "Full House", "detail": "3, 3, 3, 5, 5 · 25 points",
 "value": 25, "celebrate": false, "lament": false,
 "extras": {"combination": "full house", "points": 25, "values": [3, 3, 3, 5, 5]}}
```

`headline` ist für einen Bildschirm, `value` fürs Rechnen, `extras` für alles, was die Details
braucht. Ein Verbraucher, der das alles ignoriert, bekommt weiterhin `total`, `dice` und
`notation`.

## Was ein Modus nicht ist

Er ist keine Regel-Engine. DiceCore kennt deinen Modifikator nicht, deine Rüstungsklasse
nicht, nicht wer dran ist und nicht, *wofür* du gewürfelt hast. Es liest, was auf der Fläche
liegt, und benennt es. Alles danach gehört ins Spiel — und genau dafür gibt es die API.
