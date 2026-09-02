[English](API.md) · **Deutsch**

# Die API

`/api/v1/…` ist der Vertrag, auf den andere Projekte sich verlassen. Er ist versioniert und
wächst nur: Felder kommen dazu, innerhalb einer Version wird nichts umbenannt oder entfernt.
Alles unter `/api/setup/…` ist das eigene Backend der Weboberfläche und darf sich ohne
Vorwarnung ändern — bau nichts darauf.

Die Basis-URL ist, wo DiceCore läuft, standardmäßig `http://dicecore.local:8099`.

## Endpunkte

### `GET /api/v1/roll`

Aufnehmen und lesen. Das ist der, den du willst.

| Parameter | Standard | Bedeutung |
|---|---|---|
| `wait` | `1` | Vor dem Lesen warten, bis die Würfel liegen |
| `verify` | *(im Hintergrund)* | `1` wartet vor der Antwort auf das Fair-Play-Urteil; standardmäßig läuft die Wache hinter der Antwort und das Urteil landet auf `/state` |
| `mode` | *(eingestellter)* | Diesen Wurf als jenen Spielmodus lesen, ohne den eingestellten zu ändern |
| `store_to` | — | Datensatz-ID; legt das Bild als unbestätigtes Beispiel ab |

```json
{
  "dice": [
    {"kind": "d20", "value": 14, "box": {"x": 245, "y": 118, "w": 92, "h": 90},
     "confidence": 0.97, "alternatives": [11]},
    {"kind": "d6", "value": 4, "box": {"x": 402, "y": 210, "w": 78, "h": 77},
     "confidence": 0.99, "alternatives": []}
  ],
  "total": 18,
  "count": 2,
  "notation": "1d6+1d20 → 4, 14",
  "engine": "model",
  "at": 1788270708.61,
  "took_ms": 24.8,
  "warnings": [],
  "frame_id": null,
  "reading": {"mode": "normal", "headline": "18", "detail": "4, 14", "value": 18,
              "celebrate": false, "lament": false, "extras": {"values": [4, 14]}},
  "verdict": "clean",
  "usable": true,
  "stale": false,
  "integrity": {"verdict": "clean", "events": [], "held_s": 2.01,
                "seal": "sha256:9122ad72bc56453a19ac94c534ab4046", "settled_check": true}
}
```

So sind die Felder zu lesen:

- **`value: 0`** heißt *gefunden, aber nicht gelesen* — behandle es nie als Null. `notation`
  druckt es aus demselben Grund als `?`.
- **`confidence`** ist 0–1. Unter deiner eigenen Schwelle: neu würfeln lassen oder einen
  Menschen fragen.
- **`warnings`** ist Prosa für einen Menschen. Protokollier sie; sie erklärt eine schlechte
  Zahl.
- **`engine`** sagt, welche Erkennung sie erzeugt hat (`classic`, `model`, `remote:<url>`).
- **`usable`** ist bei genau einem Urteil falsch, `void` — die Würfel sind nicht das, was
  gelesen wurde. Prüf das und sonst nichts, wenn du über Fair Play nicht nachdenken willst;
  den Rest in [ANTI-CHEAT.de.md](ANTI-CHEAT.de.md).
- **`verdict`** beginnt als `pending` und wird ein paar Sekunden später `clean`, `disturbed`,
  `void` oder `superseded` — lies es von `/state` oder dem WebSocket, oder frag mit
  `?verify=1`. `superseded` heißt, der nächste Wurf hat vorher begonnen, und das ist normales
  Spiel.
- **`reading`** ist das, was der aktive Spielmodus aus dem Wurf gemacht hat: `headline` für
  einen Bildschirm, `value` fürs Rechnen, `extras` für die Details. Siehe
  [GAME-MODES.de.md](GAME-MODES.de.md).
- **`stale`** heißt, seit der letzten Lesung wurde nichts geworfen. Eine Anzeigetafel
  ignoriert es; alles, was Würfe zählt, darf ihn nicht doppelt zählen.

### `GET /api/v1/modes`

Jeder Spielmodus mit den erwarteten Würfeln und seinen Parametern, dazu welcher aktiv ist.
Daraus sollte die Modusauswahl eines Verbrauchers gebaut werden statt aus einer fest
verdrahteten Liste.

### `POST /api/v1/verify`

Das Urteil über den letzten Wurf fertig sprechen: die Fläche `guard.hold_s` lang beobachten,
dann mit demselben Wurf samt Urteil antworten. Für einen Aufrufer, der die Zahl mit
`verify=0` sofort genommen hat.

### `GET /api/v1/state`

Das letzte Ergebnis, ohne die Kamera anzufassen. Billig; frag so oft du willst.

### `POST /api/v1/detect`

Ein anderswo aufgenommenes Bild lesen. `multipart/form-data`, Feld `image`. Dieselbe Antwort
wie `/roll`. Das ist der Endpunkt, mit dem `engine.mode=remote` spricht — so leiht sich ein Pi
Zero die Erkennung einer stärkeren Maschine.

### `POST /api/v1/frame`

Ein Bild *in* ein DiceCore schieben, das mit `capture.source=push` eingerichtet ist. Die
Agenten-Form: ein Pi, auf dem nichts installiert ist, nimmt auf und schickt, und dieser Knoten
liest.

### `WebSocket /api/v1/events`

Ein Ergebnis wird geschoben, sobald die Würfel liegen und die Lesung sich ändert. Das sollte
ein Bot benutzen — `/roll` abzufragen nimmt bei jeder Abfrage auf.

Mit eingeschaltetem Fair Play kommt **jeder Wurf zweimal**: erst mit `verdict: "pending"` in
dem Moment, in dem die Würfel liegen, dann noch einmal mit seinem Urteil, sobald die Fläche
beobachtet wurde. Eine Anzeigetafel zeichnet den ersten; alles, was einen manipulierten Wurf
nicht anerkennen darf, handelt auf den zweiten.

### `POST /api/v1/throw`

Simulierte Würfel werfen und lesen, wie es der `Throw`-Knopf auf dem Spielbildschirm tut.
Antwortet in derselben Form wie `/roll`. **400, außer die Aufnahmequelle ist `sim`** — eine
Kamera kann nicht gebeten werden zu würfeln, denn die Würfel auf ihrer Fläche sind die, die
jemand geworfen hat.

### `GET /api/v1/dice` · `POST /api/v1/dice`

Mit welchen Würfeln dieses DiceCore spielt. `POST {"simulated": true}` schaltet auf den
Simulator, `false` zurück auf die Kamera.

```json
{"simulated": true, "source": "sim", "camera_source": "rpicam",
 "can_throw": true, "problem": null}
```

`camera_source` ist die Kamera, die „echte Würfel" auf dieser Kiste bedeutet — gemerkt statt
geraten, denn geraten ist auf allem außer einem schlichten Pi falsch. `problem` ist, warum die
gewählte Quelle nicht aufging; es wird vom POST gefüllt, statt es den ersten Wurf entdecken zu
lassen.

### `GET /api/v1/table`

Mit wem dieses DiceCore spielt.

```json
{
  "hosting": {"open": true, "seats": [{"name": "Ada", "index": 0, "remote": false,
                                       "connected": true}], "max_seats": 8},
  "guest": {"active": false, "connected": false, "seat": null, "my_turn": false,
            "address": "", "game": null},
  "can_throw": true,
  "address": "192.168.1.40:8099",
  "addresses": ["192.168.1.40:8099", "100.83.2.11:8099", "dicecore.local:8099"]
}
```

`addresses` ist jede Adresse, unter der diese Instanz sich selbst findet, beste zuerst — gib
den anderen Spielern eine davon. Während diese Instanz Gast ist, ist `guest.game` das Spiel
des Gastgebers, gespiegelt: das zeichnet der Bildschirm eines Gastes, denn ein eigenes Spiel
gibt es hier nicht.

### `POST /api/v1/table/host` · `/close` · `/join` · `/leave` · `/act`

`host` nimmt `{"name": …}` und macht einen Tisch mit diesem Namen auf Platz eins auf. `join`
nimmt `{"address": …, "name": …}` und setzt sich an einen fremden; es antwortet erst, wenn der
erste Versuch geklappt hat oder gescheitert ist, ein Tippfehler sagt das also, statt den
ganzen Abend zu wiederholen. `act` nimmt `{"action": …}` plus das, was diese Aktion braucht
(`{"action": "book", "category": "chance"}`) und schickt es zum Gastgeber — es ist die
Gast-Fassung der `/api/v1/game/…`-POSTs, die ein Spiel anfassen, das ein Gast nicht hat.

Nur wer dran ist, darf handeln, entschieden beim Gastgeber. Eine Ablehnung kommt über den
WebSocket als `{"type": "refused", "reason": "It is not your turn."}` zurück und taucht in
`guest.problem` auf.

### `WebSocket /api/v1/table`

Die Verbindung, die ein Gast offen hält. Hallo sagen, einen Platz bekommen, dann das ganze
Spiel bei jeder Änderung erhalten:

```json
→ {"type": "hello", "name": "Bob", "version": 1}
← {"type": "welcome", "seat": 1, "version": 1, "seats": [...], "game": {...}}
← {"type": "state", "game": {...}, "seats": [...], "last": {...}}
→ {"type": "action", "action": "roll", "dice": [{"kind": "d6", "value": 4, ...}]}
```

Würfe reisen als Zahlen, nie als Bilder: die eigene Erkennung jedes Spielers liest seine
eigene Fläche. Wer sich mit demselben Namen neu verbindet, bekommt denselben Platz zurück,
samt Spalte auf dem Zettel. Siehe [ONLINE.de.md](ONLINE.de.md).

### `GET /api/v1/stream.mjpg`

Ein Live-Bild der Fläche als `multipart/x-mixed-replace`, zum Spielen mit Leuten, die nicht im
Zimmer sind. **403, außer es ist eingeschaltet** unter *Setup → Camera*. Es öffnet die Kamera
nie ein zweites Mal: es schickt, was die Erkennung zuletzt aufgenommen hat, kann also nicht
mit dem Lesen um das Gerät konkurrieren.

### `GET /api/v1/health`

`{"ok": true, "name": …, "version": …}`. Für einen Supervisor oder eine Statusseite.

## Benutzen

```bash
curl http://dicecore.local:8099/api/v1/roll
```

```python
import requests

roll = requests.get("http://dicecore.local:8099/api/v1/roll", timeout=15).json()
if not roll["usable"]:                       # verdict == "void": an den Würfeln wurde manipuliert
    raise SystemExit(roll["integrity"]["events"][0]["detail"])
if any(d["value"] == 0 for d in roll["dice"]):
    raise SystemExit("Ein Würfel konnte nicht gelesen werden — siehe Reiter Training.")
print(roll["notation"], "=", roll["total"])
```

```python
# Ein Bot: auf jeden Wurf reagieren, während er passiert.
import json, websockets, asyncio

async def watch():
    async with websockets.connect("ws://dicecore.local:8099/api/v1/events") as socket:
        async for message in socket:
            roll = json.loads(message)
            if "error" not in roll:
                print(roll["notation"])

asyncio.run(watch())
```

```javascript
const roll = await (await fetch("http://dicecore.local:8099/api/v1/roll")).json();
console.log(roll.total, roll.notation);
```

## Datensätze

`GET /api/setup/sets/{id}/export.zip` gibt den ganzen Satz als Zip heraus — Bilder, Etiketten
und seine Beschreibung. `POST /api/setup/sets/import` nimmt einen zurück, immer als neuen
Satz. So kommen die Würfel eines Freundes in dein Modell.

## Die andere Richtung

DiceCore kann jeden fertigen Wurf auch von sich aus weiterreichen — in einen Discord-Kanal, in
eine Avrae-Variable oder als JSON an eine URL deiner Wahl. Siehe [AVRAE.de.md](AVRAE.de.md).

## Direkt in Python einbinden

Für etwas, das auf derselben Maschine läuft, HTTP überspringen:

```python
from dicecore.config import Settings
from dicecore.reader import Reader

reader = Reader(Settings.load()[0])
result = reader.read()
print(result.total, result.notation)
```

`Reader` ist dasselbe Objekt, das auch der Server hält, das Verhalten ist also identisch —
aber nur ein Prozess darf die Kamera zugleich besitzen.

## Stabilitätsversprechen

Innerhalb von `v1`:

- Felder kommen dazu, werden nie entfernt oder umbenannt.
- `kind`-Werte kommen aus einem festen Vokabular: `d4 d6 d8 d10 d100 d12 d20`.
- Modus-IDs kommen nur dazu. Ein Verbraucher, der eine nicht kennt, sollte auf `total` und
  `dice` zurückfallen, die jeder Modus weiterhin füllt.
- `value` ist `0` für „nicht gelesen", `0–9` bei einem d10, `0/10/…/90` bei einem d100, sonst
  `1..Flächen`.
- `verdict` ist eines von `unverified`, `pending`, `clean`, `disturbed`, `void`, `superseded`;
  `usable` ist nur bei `void` falsch. Neue Urteile werden, wenn überhaupt, *spezifischer* sein
  — behandle ein unbekanntes als benutzbar und lies `usable`.
- HTTP 200 mit einer `warnings`-Liste ist der normale Weg, eine unvollständige Lesung zu
  melden. Ein 4xx/5xx trägt `{"error": …, "detail": …}`, wobei `detail` ein Satz ist, den du
  einem Benutzer zeigen kannst.
