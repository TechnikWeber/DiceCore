**English** · [Deutsch](API.de.md)

# The API

`/api/v1/…` is the contract other projects depend on. It is versioned, and it only ever
grows: fields get added, nothing gets renamed or removed inside a version. Anything under
`/api/setup/…` is the web UI's own back end and may change without warning — do not build on
it.

Base URL is wherever DiceCore runs, `http://dicecore.local:8099` by default.

## Endpoints

### `GET /api/v1/roll`

Capture and read. This is the one you want.

| Query | Default | Meaning |
|---|---|---|
| `wait` | `1` | Wait for the dice to settle before reading |
| `verify` | *(background)* | `1` waits for the fair-play verdict before answering; by default the watch runs behind the answer and the verdict lands on `/state` |
| `mode` | *(configured)* | Read this roll as that game mode, without changing the configured one |
| `store_to` | — | Dataset set id; files the frame as an unconfirmed sample |

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

Read the fields like this:

- **`value: 0`** means *located but not read* — never treat it as a zero. `notation` prints
  it as `?` for the same reason.
- **`confidence`** is 0–1. Below your own threshold, ask for a reroll or ask a human.
- **`warnings`** is prose meant for a person. Log it; it is what explains a bad number.
- **`engine`** tells you which engine produced it (`classic`, `model`, `remote:<url>`).
- **`usable`** is false for exactly one verdict, `void` — the dice are not what was read.
  Check this and nothing else if you do not want to think about fair play; see
  [ANTI-CHEAT.md](ANTI-CHEAT.md) for the rest.
- **`verdict`** starts as `pending` and becomes `clean`, `disturbed`, `void` or `superseded`
  a couple of seconds later — read it from `/state` or the websocket, or ask for
  `?verify=1`. `superseded` means the next throw began first, which is normal play.
- **`reading`** is what the active game mode made of the roll: `headline` for a screen,
  `value` for arithmetic, `extras` for the detail. See [GAME-MODES.md](GAME-MODES.md).
- **`stale`** means nothing was thrown since the last reading. A scoreboard ignores it;
  anything that counts rolls must not count it twice.

### `GET /api/v1/modes`

Every game mode with its expected dice and its parameters, plus which one is active. This is
what a consumer's own mode picker should be built from rather than a hardcoded list.

### `POST /api/v1/verify`

Finish judging the last roll: watch the tray for `guard.hold_s`, then answer with the same
roll carrying its verdict. For a caller that took the number immediately with `verify=0`.

### `GET /api/v1/state`

The last result, without touching the camera. Cheap; poll it freely.

### `POST /api/v1/detect`

Read an image captured elsewhere. `multipart/form-data`, field `image`. Same response as
`/roll`. This is the endpoint `engine.mode=remote` talks to, which is how a Pi Zero borrows
a stronger machine's engine.

### `POST /api/v1/frame`

Push a frame *into* a DiceCore that is configured with `capture.source=push`. The agent
shape: a Pi with nothing installed captures and POSTs, and this node reads.

### `WebSocket /api/v1/events`

A result is pushed as soon as the dice settle and the reading changes. This is what a bot
should use — polling `/roll` captures on every poll.

With fair play on, **every roll arrives twice**: first with `verdict: "pending"` the moment
the dice settle, then again with its verdict once the tray has been watched. A scoreboard
renders the first; anything that must not honour a tampered roll acts on the second.

### `POST /api/v1/throw`

Roll simulated dice and read them, as the `Throw` button on the game screen does. Answers
with the same shape as `/roll`. **400 unless the capture source is `sim`** — a camera cannot
be asked to roll, because the dice on its tray are the ones somebody threw.

### `GET /api/v1/dice` · `POST /api/v1/dice`

Which dice this DiceCore plays with. `POST {"simulated": true}` switches to the simulator,
`false` switches back to the camera.

```json
{"simulated": true, "source": "sim", "camera_source": "rpicam",
 "can_throw": true, "problem": null}
```

`camera_source` is the camera "real dice" means on this box — remembered rather than
guessed, because a guess is wrong on anything but a plain Pi. `problem` is why the chosen
source would not open, filled in by the POST rather than left for the first throw to
discover.

### `GET /api/v1/table`

Who this DiceCore is playing with.

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

`addresses` is every address this instance can find itself at, best first — hand one of them
to the other players. While this instance is a guest, `guest.game` is the host's game,
mirrored: that is what a guest's screen draws, because there is no game of its own here.

### `POST /api/v1/table/host` · `/close` · `/join` · `/leave` · `/act`

`host` takes `{"name": …}` and opens a table with that name in seat one. `join` takes
`{"address": …, "name": …}` and sits down at somebody else's; it answers only once the first
attempt has succeeded or failed, so a typo says so instead of retrying all evening. `act`
takes `{"action": …}` plus whatever that action needs (`{"action": "book", "category":
"chance"}`) and sends it to the host — it is the guest's version of the `/api/v1/game/…`
POSTs, which touch a game a guest does not have.

Only the player whose turn it is may act, decided at the host. A refusal comes back on the
websocket as `{"type": "refused", "reason": "It is not your turn."}` and shows up in
`guest.problem`.

### `WebSocket /api/v1/table`

The connection a guest holds open. Say hello, get a seat, then receive the whole game every
time it changes:

```json
→ {"type": "hello", "name": "Bob", "version": 1}
← {"type": "welcome", "seat": 1, "version": 1, "seats": [...], "game": {...}}
← {"type": "state", "game": {...}, "seats": [...], "last": {...}}
→ {"type": "action", "action": "roll", "dice": [{"kind": "d6", "value": 4, ...}]}
```

Rolls travel as numbers, never as pictures: each player's own engine reads their own tray.
Reconnecting with the same name gets the same seat back, scorecard column and all. See
[ONLINE.md](ONLINE.md).

### `GET /api/v1/stream.mjpg`

A live view of the tray as `multipart/x-mixed-replace`, for playing with people who are not
in the room. **403 unless switched on** under *Setup → Camera*. It never opens the camera a
second time: it sends whatever the reader last captured, so it cannot compete with the
reading for the device.

### `GET /api/v1/health`

`{"ok": true, "name": …, "version": …}`. For a supervisor or a status page.

## Using it

```bash
curl http://dicecore.local:8099/api/v1/roll
```

```python
import requests

roll = requests.get("http://dicecore.local:8099/api/v1/roll", timeout=15).json()
if not roll["usable"]:                       # verdict == "void": the dice were interfered with
    raise SystemExit(roll["integrity"]["events"][0]["detail"])
if any(d["value"] == 0 for d in roll["dice"]):
    raise SystemExit("A die could not be read — check the Training tab.")
print(roll["notation"], "=", roll["total"])
```

```python
# A bot: react to every roll as it happens.
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

## Datasets

`GET /api/setup/sets/{id}/export.zip` hands the whole set over as a zip — frames, labels and
its description. `POST /api/setup/sets/import` takes one back, always as a new set. That is
how a friend's dice reach your model.

## The other direction

DiceCore can also hand each finished roll over by itself — into a Discord channel, into an
Avrae variable, or as JSON to a URL of yours. See [AVRAE.md](AVRAE.md).

## Embedding it in Python directly

For something running on the same machine, skip HTTP:

```python
from dicecore.config import Settings
from dicecore.reader import Reader

reader = Reader(Settings.load()[0])
result = reader.read()
print(result.total, result.notation)
```

`Reader` is the same object the server holds, so the behaviour is identical — but only one
process may own the camera at a time.

## Stability promise

Within `v1`:

- Fields are added, never removed or renamed.
- `kind` values come from a fixed vocabulary: `d4 d6 d8 d10 d100 d12 d20`.
- Mode ids only ever get added. A consumer that does not recognise one should fall back to
  `total` and `dice`, which every mode still fills in.
- `value` is `0` for "not read", `0–9` for a d10, `0/10/…/90` for a d100, `1..faces`
  otherwise.
- `verdict` is one of `unverified`, `pending`, `clean`, `disturbed`, `void`, `superseded`;
  `usable` is false only for `void`. New verdicts, if any, will be *more* specific — treat an unknown
  one as usable and read `usable`.
- HTTP 200 with a `warnings` list is the normal way a partial reading is reported. A 4xx/5xx
  carries `{"error": …, "detail": …}` where `detail` is a sentence you can show a user.
