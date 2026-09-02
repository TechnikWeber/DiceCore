[English](ANTI-CHEAT.md) · **Deutsch**

# Fair Play

DiceCore beobachtet die Landefläche, nachdem es die Würfel gelesen hat, und sagt dir, ob die
Zahl, die es dir gegeben hat, noch stimmt. Diese Seite ist, was es erwischt, was nicht, und
wie man es einstellt.

## Wovon es zuerst ehrlich sein muss

**Das ist Manipulations-*erkennung*, keine Manipulations-*sicherheit*.** DiceCore beobachtet
die Fläche mit derselben Kamera, mit der es die Würfel liest — wer diese Kamera beherrscht,
kann es aushebeln: Objektiv abdecken, Halterung anstoßen, Konfiguration ändern, eine Aufnahme
einspeisen. Daran wird nichts in Kameraform je etwas ändern.

Gut ist es in dem Schummeln, das an einem Tisch tatsächlich passiert: eine Hand, die noch
einmal hineingeht, um einen Würfel umzudrehen, ein Würfel, der angestoßen wird, während das
Gespräch weiterläuft, derselbe Glückswurf zweimal gemeldet. Das ist alles *sichtbar*, und
DiceCore behauptet nie, ein Wurf sei fair gewesen. Es sagt entweder „zwischen dem Wurf und
dieser Zahl ist nichts passiert" oder „hier ist genau, was passiert ist", und dein Spiel
entscheidet, was das wert ist.

### Aus der Ferne spielen

Für ein Spiel über einen Videoanruf ist das ehrliche Instrument nicht die Wache, sondern das
**Live-Bild** (`/api/v1/stream.mjpg`, *Setup → Camera*): die Mitspieler sehen die Würfel
fallen und sehen die Zahl im selben Moment erscheinen. Überzeugender wird es mit Würfeln kaum,
und es überzeugt aus demselben Grund wie der Bildschirm über dem Turm — die Zahl wird
öffentlich, bevor irgendwer sie ändern könnte.

Für sich genommen beweist es natürlich nichts. Ein Stream lässt sich überallhin richten, und
wer die Kamera beherrscht, beherrscht beides. Es ist ein Beleg zwischen Leuten, die ohnehin in
gutem Glauben spielen, und das ist fast alles hiervon.

### Die Wache ist die zweite Linie, nicht die erste

Es lohnt sich, klar zu sagen, was hier die eigentliche Arbeit tut. Die Zahl wird aufgenommen,
**wenn die Würfel zur Ruhe kommen**, und nichts, was danach mit der Fläche geschieht, kann
ändern, was DiceCore aufgezeichnet hat. Die Wache schützt also nicht die Zahl — das tut der
Zeitpunkt.

Wofür die Wache tatsächlich da ist:

1. **Ein Würfel, der zu spät zur Ruhe kommt.** Wenn einer noch wackelte, als der Ruhetest
   bestand, ist die Lesung falsch, und die Fläche widerspricht ihr jetzt. Das zweite Lesen
   erwischt das. Das ist ein Korrektheitsproblem, kein Schummelproblem, und wahrscheinlich das
   Wertvollste hier.
2. **Bildschirm und Tisch in Übereinstimmung halten.** Menschen glauben den Würfeln vor sich.
   Wenn die API 6 sagt und die Fläche 8, weil jemand einen umgedreht hat, gibt es Streit; die
   Aufzeichnung entscheidet ihn.
3. **Die Prüfungen, die gar nichts mit dem Haltefenster zu tun haben** — `stale`, ein
   eingefrorenes Bild, ein abgedecktes Objektiv —, die beim Lesen passieren und schon für sich
   nützlich wären.

Und die stärkste Maßnahme von allen steht nicht in dieser Datei: **ein Bildschirm, der die
Zahl in dem Moment zeigt, in dem sie gelesen wird**, macht nachträgliches Umdrehen sinnlos,
weil alle die Zahl schon gesehen haben. Siehe [DISPLAYS.de.md](DISPLAYS.de.md). Eine rote
Lampe, die „Hände weg" sagt, und eine grüne, die „wirf" sagt, tun für einen fairen Tisch mehr
als jedes Maß an Beobachtung.

Setz es nicht ein, wo Geld auf dem Spiel steht, und mach es nicht zum Schiedsrichter, den
niemand überstimmen kann.

## Der Ablauf

```
geworfen ──► rollt ──► liegt still ──► LESEN ──► gehalten ──► Urteil
             settle.py                 engine   guard.py
```

1. **Das Zur-Ruhe-Kommen** beantwortet, *wann* geschaut wird. Die Kamera beobachtet die
   Bilddifferenz und liest, sobald das Bild ein paar Einzelbilder hintereinander ruhig war —
   keine feste Wartezeit, denn „zwei Sekunden" ist zu langsam für einen flach landenden d6 und
   zu schnell für einen d20, der die Rampe hinunterrollt. Mitten im Rollen wird nie gelesen.
2. **Das Lesen** passiert, und die Zahl ist sofort verfügbar.
3. **Das Halten.** Für `hold_s` Sekunden bleibt die Fläche beobachtet. Alles, was sich bewegt,
   wird aufgezeichnet.
4. **Das zweite Lesen.** Am Ende des Haltens werden die Würfel ein zweites Mal gelesen und mit
   dem verglichen, was veröffentlicht wurde. Das passiert auch, wenn nichts gesehen wurde,
   denn ein schnell genug umgedrehter Würfel kann vollständig zwischen zwei Bildern liegen.

## Die Urteile

| Urteil | Bedeutet | `usable` |
|---|---|---|
| `clean` | Bis zum Ende des Haltens beobachtet; nichts hat die Fläche berührt | ja |
| `disturbed` | Etwas ist hineingelangt — die Würfel lesen sich gleich, oder die Richtlinie markiert nur | ja |
| `void` | Die Würfel sind **nicht** das, was gelesen wurde | **nein** |
| `pending` | Die Zahl ist draußen; das Haltefenster ist noch nicht vorbei | ja |
| `superseded` | Der nächste Wurf begann, bevor die Wache dieses Wurfs fertig war | ja |
| `unverified` | Fair Play ist aus, oder der Aufrufer wollte nicht warten | ja |

`usable` ist bei genau einem Urteil falsch, ein Verbraucher kann das also beachten, ohne
irgendetwas darüber zu wissen, wie das Beobachten funktioniert:

```python
roll = requests.get(".../api/v1/roll").json()
if not roll["usable"]:
    raise Cheating(roll["integrity"]["events"])
```

## Was es erwischt

**Eine Hand auf der Fläche.** Veränderungsbereiche, die groß genug sind und den Bildrand
erreichen, heißen *reach* — ein Arm muss von außen hineinkommen. Der reach allein verwirft
nichts: der häufige Fall ist jemand, der sein Getränk am Turm vorbeiholt, und dafür einen
rechtmäßigen Wurf wegzuwerfen ist schlimmer als das Schummeln, das es verhindert. Er wird
aufgezeichnet, und er ist der Grund, warum das zweite Lesen zählt.

**Würfel, die sich verändert haben.** Die entscheidende Prüfung. Drei getrennte Vergleiche,
denn es sind drei verschiedene Betrügereien:

- *wie viele* — ein Würfel dazugelegt oder verschwunden
- *was sie zeigen* — ein Würfel umgedreht
- *wo sie liegen* — ein Würfel angestoßen, ob die Fläche sich änderte oder nicht (eine
  Verschiebung um mehr als `move_tolerance` der eigenen Würfelgröße)

**Derselbe Wurf zweimal gemeldet.** Mit `require_throw` wird eine Lesung, der keine echte
Bewegung vorausging und die sich identisch zur letzten liest, als `stale` markiert und sagt
das auch. Anzeigemodi ignorieren es; alles, was Würfe zählt, darf ihn nicht doppelt zählen.

**Ein eingefrorenes oder abgespieltes Bild.** Zwei Aufnahmen eines echten Sensors sind nie
identisch — allein das Rauschen garantiert das. Identische Aufnahmen hintereinander bedeuten
daher, dass das Bild eingefroren ist oder in Schleife läuft, nicht dass die Würfel still
liegen, und das ist ein Fehler. (Verglichen werden die Rohbilder. Die verkleinerten, die die
Bewegungserkennung benutzt, werden auf jedem ruhigen Tisch identisch, und dort zu prüfen
erklärte jeden ehrlichen Wurf zur Fälschung.) Bei Quellen, die absichtlich wiederholen, wird
die Prüfung übersprungen — dem Ordner-Simulator und hineingeschickten Bildern.

**Ein abgedecktes Objektiv.** Wenn die Helligkeit auf einen Bruchteil der des Lesebildes
einbricht, ist das ein Fehler.

**Eine Kamera, die mitten im Halten aussteigt.** Wird als Fehler aufgezeichnet, statt
abzustürzen und den Wurf zu verlieren.

## Was es nicht erwischt

- Alles, was **vor** dem Zur-Ruhe-Kommen passiert: ein gezinkter Würfel, ein kontrollierter
  Wurf, ein von Hand hingelegter statt geworfener Würfel. DiceCore liest, was landet; es weiß
  nicht, wie es dorthin kam. (`require_throw` beweist nur, dass sich *etwas* bewegt hat, nicht
  dass fair geworfen wurde.)
- Ein Würfel, der gegen einen identisch aussehenden mit derselben Fläche getauscht wird.
- Manipulation unter einer Hand, die nie weggeht: bleibt die Fläche das ganze Halten über
  bedeckt und sind die Würfel danach unverändert, wird der reach aufgezeichnet, aber die
  Lesung steht.
- Überhaupt nichts mehr, sobald das Haltefenster zu ist. `hold_s` ist, wie lange das
  Versprechen gilt.
- Nichts nach Beginn des nächsten Wurfs: dieser Wurf wird `superseded` markiert, und das zu
  Recht.
- Jemanden mit Zugriff auf den Pi, die Kamera oder die Konfiguration.

## Einstellungen

**Detection → Fair play** in der Weboberfläche, oder `guard` in der Konfigurationsdatei.

| Einstellung | Standard | Was sie tut |
|---|---|---|
| `enabled` | `true` | Die Fläche nach einer Lesung beobachten |
| `policy` | `flag` | `off`, `flag` (melden und markieren), `void` (einen gestörten Wurf verwerfen) |
| `hold_s` | `2.0` | Wie lange Hände von der Fläche wegbleiben müssen |
| `interval_s` | `0.15` | Wie oft während des Haltens geschaut wird |
| `motion_threshold` | `2.0` | Bilddifferenz (0–255), die als Vorgang zählt |
| `hand_area_frac` | `0.05` | Eine Veränderung dieses Bildanteils gilt als Hand |
| `move_tolerance` | `0.4` | Wie weit ein Würfel driften darf, als Anteil seiner eigenen Größe |
| `void_on_touch` | `false` | Unter `void` auch verwerfen, wenn die Würfel sich nicht änderten |
| `require_throw` | `true` | Eine Lesung ohne vorherigen Wurf als `stale` markieren |
| `freeze_frames` | `6` | Identische Aufnahmen hintereinander, die ein eingefrorenes Bild bedeuten |
| `dark_fraction` | `0.35` | Helligkeit unter diesem Anteil des Lesebildes ist ein abgedecktes Objektiv |

### Welche Richtlinie

- **`flag`** (Standard) für einen Spieleabend. Jeder bekommt seine Zahl; das Protokoll sagt,
  was passiert ist. Niemandem wird je etwas weggenommen, weil er nach dem Salz gegriffen hat.
- **`void`** für einen Turniertisch oder einen Bot, der auszahlt. Eine veränderte Lesung
  ergibt gar keine Zahl. Nimm `void_on_touch` dazu, wo nichts auf die Fläche darf — und rechne
  damit, die Regel erklären zu müssen, bevor die Leute sie auf die harte Tour lernen.
- **`off`**, wenn DiceCore eine Anzeige ist und niemand im Wettbewerb steht.

### Was es kostet, und warum fast nichts

Das Beobachten verzögert die Zahl nicht. `GET /api/v1/roll` antwortet, sobald die Würfel
gelesen sind — etwa eine Fünftelsekunde, nachdem sie liegen — mit `verdict: "pending"`, und
das Haltefenster läuft dahinter auf einem eigenen Thread. Das Urteil landet ein paar Sekunden
später auf `/api/v1/state` und auf dem WebSocket.

```bash
curl http://dicecore.local:8099/api/v1/roll              # Zahl sofort, Urteil "pending"
curl http://dicecore.local:8099/api/v1/state             # derselbe Wurf, mit Urteil
curl "http://dicecore.local:8099/api/v1/roll?verify=1"   # oder gleich darauf warten
```

**Du musst nie warten, um wieder zu würfeln.** Ein neuer Wurf bricht die vorherige Wache ab
und markiert diesen Wurf als `superseded`; verworfen wird er nicht. `hold_s` ist, wie lange
die Fläche für ein *sauberes* Urteil in Ruhe gelassen werden muss, keine Sperre.

Der WebSocket nimmt dir das ab: jeder Wurf kommt zweimal an, erst als `pending`, dann mit
seinem Urteil. Eine Anzeigetafel zeichnet den ersten; ein Bot, der einen manipulierten Wurf
nicht anerkennen darf, handelt auf den zweiten.

## Die Aufzeichnung lesen

Jeder geprüfte Wurf trägt einen `integrity`-Block:

```json
{
  "verdict": "disturbed",
  "events": [
    {"kind": "reach", "severity": "warn",
     "detail": "something entered the tray from outside (11% of the frame)", "at": 1788272490.5},
    {"kind": "unchanged", "severity": "info",
     "detail": "the tray was disturbed but the dice read the same afterwards", "at": 1788272491.0}
  ],
  "held_s": 2.01,
  "seal": "sha256:9122ad72bc56453a19ac94c534ab4046",
  "settled_check": true
}
```

- `severity` ist `info` (eine Notiz), `warn` (zeigenswert) oder `fault` (verwirft unter
  `void`).
- Jede Art wird **einmal** pro Wurf aufgezeichnet: eine zwei Sekunden über der Fläche
  gehaltene Hand ist ein reach, nicht vierzig.
- `seal` kennzeichnet genau diesen Wurf — das Bild plus das, was daraus gelesen wurde.
  Protokollier es, und eine Zahl lässt sich später auf das Bild zurückführen, das sie erzeugt
  hat.
- `settled_check` ist nur dann falsch, wenn die zweite Lesung nicht genommen werden konnte.
