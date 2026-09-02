[English](AVRAE.md) · **Deutsch**

# Avrae, Discord und alles andere

DiceCore liest echte Würfel. Was ein Tisch als Nächstes meist will, ist, dass diese Zahl dort
auftaucht, wo das Spiel ohnehin stattfindet. Das ist die ausgehende Hälfte der API: statt dass
jemand DiceCore nach einem Wurf fragt, reicht DiceCore jeden fertigen Wurf weiter.

Alles hier ist **standardmäßig aus**, und zwei von drei tragen ein Zugangsgeheimnis.
**Setup → API → Send rolls out.**

## Was Avrae kann und was nicht

**Avrae würfelt selbst und lässt sich nicht dazu bringen, deine Würfel zu benutzen.** Es gibt
keinen Weg, `!check athletics` den d20 auf deinem Tisch fragen zu lassen — nicht über dieses
Projekt und über kein anderes, denn Avraes Würfel sind Avraes. Wer dir etwas anderes erzählt,
rät.

Was *möglich* ist, und was hier passiert:

1. DiceCore schreibt jeden Wurf in eine **Benutzervariable** von Avrae, über Avraes eigene
   API.
2. Ein einzeiliger **Alias** in Discord liest diese Variable wieder aus.

Du tippst weiterhin etwas in Discord. Die *Zahl* kommt von deinem Tisch.

### Zwei Arten von Alias, und der Unterschied zählt

**`!phys` — zeig, was ich geworfen habe.** Avrae druckt deinen Wurf. Einfach und sicher
funktionierend.

**`!pr` — lass Avrae meine Zahl würfeln.** Das ist das, worauf die meisten hinauswollen. Es
gibt Avrae einen Würfel, der *nur* auf dem landen kann, was du geworfen hast — `1d20mi17ma17`
ist ein d20, festgeklemmt auf 17 — also läuft das Ergebnis durch Avraes eigenen Würfler und
kommt in Avraes eigenem Format heraus, samt Boni. `!pr +5` nach einem Wurf von 17 gibt dir
Avrae, das 17+5 würfelt.

Was es weiterhin nicht ist: `!check athletics` fragt deinen Tisch nicht. Wenn du den echten
Würfel in einer Probe haben willst, baust du den Alias, der das tut — und das hier ist die
Form, aus der du ihn baust.

**Was geprüft ist und was nicht.** Die API, in die hier geschrieben wird, ist gegen Avraes
eigenen Quellcode geprüft. Die Aliase nicht — ich habe kein Avrae-Konto, um sie
auszuprobieren, und der Klemm-Trick hängt an einer Würfelsyntax, die sich verschoben haben
kann. Probier sie erst in einem ruhigen Kanal.

Geprüft gegen Avraes eigenen Quellcode (`avrae/avrae-service`,
`blueprints/customizations.py` und `avrae/avrae`, `aliasing/evaluators.py`):

```
POST https://api.avrae.io/customizations/uvars/<name>
Authorization: <Token von avrae.io/dashboard>
Content-Type: application/json

{"value": "…"}
```

und, in einem Alias, `get_uvar(name)` / `uvar_exists(name)`.

## Einrichten

1. **Token holen.** Bei [avrae.io/dashboard](https://avrae.io/dashboard) anmelden und das
   API-Token kopieren. Es ist ein Zugangsgeheimnis für dieses Avrae-Konto — es kann dessen
   Aliase und Variablen lesen und schreiben — und DiceCore legt es im Klartext in seiner
   Konfigurationsdatei ab. Gut zu wissen, bevor man eines auf eine Maschine legt, die andere
   erreichen können.
2. **Einfügen** unter *Setup → API → Avrae*, **Send finished rolls** und **Write rolls to an
   Avrae variable** einschalten, speichern.
3. **„Send a test roll" drücken.** Es wartet auf Avraes Antwort, statt zu feuern und zu
   vergessen — ein falsches Token sagt das also sofort.
4. **Den Alias einmal in Discord einfügen.** Die Seite zeigt ihn mit Kopierknopf, schon mit
   dem Variablennamen, den du gewählt hast:

```
!alias phys echo <drac2>
if not uvar_exists("dicecore"):
    return "No physical roll yet — throw the dice."
r = load_json(get_uvar("dicecore"))
faces = ", ".join([str(d["kind"]) + " " + str(d["value"]) for d in r["dice"]])
out = "**" + str(r["total"]) + "**  (" + faces + ")"
if not r["usable"]:
    out = out + "  ⚠️ voided — the dice changed after they were read"
return out
</drac2>
```

Jetzt die Würfel werfen und `!phys` tippen.

Der Alias ist absichtlich ohne f-Strings und ohne Kunststücke geschrieben: es geht darum, dass
er auf einem fremden Avrae beim ersten Versuch funktioniert, nicht darum, dass er elegant ist.

### Was in der Variable steht

```json
{"total": 21, "notation": "1d6+1d20 → 4, 17",
 "dice": [{"kind": "d20", "value": 17}, {"kind": "d6", "value": 4}],
 "verdict": "clean", "usable": true, "at": 1788362021.9,
 "headline": "21", "mode": "rpg"}
```

Klein und flach, denn eine Variable hat eine Größengrenze, und ein Draconic-Alias will die
Felder, die er benutzt, nicht die Kästchen, in denen die Würfel gefunden wurden. Lies
`usable`, falls es dir wichtig ist: es ist nur dann falsch, wenn die Fair-Play-Wache gesehen
hat, dass die Würfel sich nach dem Lesen verändert haben.

### In eigenen Aliassen benutzen

Der Wert gehört dir, sobald `load_json` ihn hat, und der Klemm-Trick von oben verallgemeinert
sich: `1d20mi{v}ma{v}` ist der echte Würfel, ausgedrückt in Avraes eigener Würfelsprache —
überall, wo ein Befehl einen Würfelausdruck nimmt, nimmt er also deinen Wurf. Welches Flag der
Befehl an deinem Tisch benutzt, hängt vom Befehl ab.

## Discord, ohne Avrae

Einfacher und völlig zuverlässig: eine Webhook-Nachricht in einem Kanal, damit alle den echten
Wurf sehen, während er fällt.

*Kanaleinstellungen → Integrationen → Webhooks → Neuer Webhook → URL kopieren*, einfügen unter
*Setup → API → Discord*, fertig. Nachrichten sehen so aus:

> 🎲 **21** — 4, 17

mit einer angehängten Notiz, wenn die Fair-Play-Wache etwas zu dem Wurf zu sagen hat.

Eines ist zu wissen: Discord behandelt Webhook-Nachrichten als Bot-Nachrichten, und **Bots
lösen keine anderen Bots aus**. Ein Webhook-Beitrag kann Avrae zu gar nichts bringen — und
genau dafür gibt es den uvar-Weg oben.

## Sonst wohin

*Setup → API → Anywhere else* schickt dasselbe JSON, das die API für einen Wurf zurückgibt,
per POST an eine URL deiner Wahl, sobald es passiert. Das ist die Naht für einen eigenen Bot,
eine Anzeigetafel, eine Tabelle oder die Brücke zu dem Dienst, der nicht in dieser Liste
steht.

## Wie es sich verhält

- **Immer auf einem Thread.** Ein Webhook an einer schlechten Verbindung dauert Sekunden, und
  nichts außerhalb von DiceCore darf das Lesen eines Würfels verlangsamen.
- **Verschickt, sobald das Urteil steht**, nicht in dem Moment, in dem die Zahl existiert — ein
  Wurf, den die Fair-Play-Wache verwirft, erreicht also niemandes Spiel. Schalt *Skip rolls the
  fair-play watch voided* aus, wenn du lieber alles sehen willst.
- **Eine fehlgeschlagene Zustellung wird notiert und vergessen.** Keine Wiederholungen: ein
  Würfelwurf ist ungefähr zehn Sekunden interessant, und eine Warteschlange alter Würfe ist
  schlimmer als keine. Die letzten Versuche stehen unter den Einstellungen.
- **Zugangsgeheimnisse werden nie wieder herausgegeben.** Die Seite kann sagen, *ob* ein Token
  gesetzt ist; sie kann dir das Token nicht zeigen.
