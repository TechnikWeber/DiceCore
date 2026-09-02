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
| `verify` | *(config)* | Also watch the tray afterwards — **blocks for `guard.hold_s`**. `0` answers at once with `verdict: "pending"` |
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
- **`stale`** means nothing was thrown since the last reading. A scoreboard ignores it;
  anything that counts rolls must not count it twice.

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
- `value` is `0` for "not read", `0–9` for a d10, `0/10/…/90` for a d100, `1..faces`
  otherwise.
- `verdict` is one of `unverified`, `pending`, `clean`, `disturbed`, `void`; `usable` is
  false only for `void`. New verdicts, if any, will be *more* specific — treat an unknown
  one as usable and read `usable`.
- HTTP 200 with a `warnings` list is the normal way a partial reading is reported. A 4xx/5xx
  carries `{"error": …, "detail": …}` where `detail` is a sentence you can show a user.
