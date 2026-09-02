**English** · [Deutsch](ANTI-CHEAT.de.md)

# Fair play

DiceCore watches the tray after it has read the dice, and tells you whether the number it
gave you is still true. This page is what it can catch, what it cannot, and how to set it.

## What it is honest about first

**This is tamper evidence, not tamper proof.** DiceCore watches the tray with the same
camera it reads the dice with, so anyone who controls that camera — covers the lens, nudges
the mount, edits the config, feeds it a recording — can defeat it. Nothing camera-shaped
will ever change that.

What it is good at is the cheating that actually happens at a table: a hand going back in to
turn a die over, a die nudged while the conversation moves on, the same lucky roll reported
twice. Those are all *visible*, and DiceCore never claims a roll was fair. It says either
"nothing happened between the throw and this number" or "here is exactly what happened", and
your game decides what that is worth.

### Playing at a distance

For a game played over a video call, the honest instrument is not the watch but the
**live view** (`/api/v1/stream.mjpg`, *Setup → Camera*): the people you are playing with see
the dice land and see the number appear at the same moment. That is about as convincing as
dice get, and it convinces for the same reason the screen over the tower does — the number
becomes public before anybody could change it.

It proves nothing on its own, of course. A stream can be pointed anywhere and anything that
controls the camera controls both. It is evidence between people who are already playing in
good faith, which is what almost all of this is.

### The watch is the second line, not the first

Worth being clear about what does the real work here. The number is captured **when the dice
settle**, and nothing done to the tray afterwards can change what DiceCore recorded. So the
watch does not protect the number — the timing does.

What the watch is actually for:

1. **A die that settles late.** If one was still rocking when the stillness test passed, the
   reading is wrong and the tray now disagrees with it. The re-read catches that. This is a
   correctness problem, not a cheating one, and it is probably the most valuable thing here.
2. **Keeping the screen and the table in agreement.** People believe the dice in front of
   them. If the API says 6 and the tray says 8 because somebody flipped one, there is an
   argument; the record settles it.
3. **The checks that are not about the hold window at all** — `stale`, a frozen feed, a
   covered lens — which happen at read time and would be worth having on their own.

And the strongest measure of all is not in this file: **a screen showing the number the
instant it is read** makes post-hoc flipping pointless, because everyone has already seen
the number. See [DISPLAYS.md](DISPLAYS.md). A red lamp that says "hands off" and a green one
that says "throw" do more for a fair table than any amount of watching.

Do not use it where money is at stake, and do not make it the referee nobody can overrule.

## The sequence

```
thrown ──► tumbling ──► still ──► READ ──► held ──► verdict
           settle.py            engine    guard.py
```

1. **Settling** answers *when* to look. The camera watches the frame difference and reads
   once the picture has been quiet for a few frames in a row — no fixed wait, because "two
   seconds" is too slow for a d6 that lands flat and too fast for a d20 that rolls off the
   ramp. Nothing is ever read mid-tumble.
2. **The reading** happens, and the number is available immediately.
3. **The hold.** For `hold_s` seconds the tray stays watched. Anything that moves is
   recorded.
4. **The re-read.** At the end of the hold the dice are read a second time and compared with
   what was published. This happens even when nothing was seen, because a die turned over
   quickly enough can sit entirely between two frames.

## The verdicts

| Verdict | Means | `usable` |
|---|---|---|
| `clean` | Watched to the end of the hold; nothing touched the tray | yes |
| `disturbed` | Something reached in — the dice still read the same, or the policy only flags | yes |
| `void` | The dice are **not** what was read | **no** |
| `pending` | The number is out; the hold window has not finished | yes |
| `superseded` | The next throw began before this roll's watch finished | yes |
| `unverified` | Fair play is switched off, or the caller asked not to wait | yes |

`usable` is false for exactly one verdict, so a consumer can respect this without knowing
anything about how the watching works:

```python
roll = requests.get(".../api/v1/roll").json()
if not roll["usable"]:
    raise Cheating(roll["integrity"]["events"])
```

## What it catches

**A hand in the tray.** Change regions large enough and reaching the frame edge are called a
*reach* — an arm has to come in from outside. The reach alone does not void anything: the
common case is someone getting their drink past the tower, and throwing away a legitimate
roll for that is worse than the cheating it prevents. It is recorded, and it is what makes
the re-read matter.

**Dice that changed.** The decisive check. Three separate comparisons, because they are
three different cheats:

- *how many* — a die added or palmed
- *what they show* — a die turned over
- *where they are* — a die nudged, whether or not the face changed (a drift of more than
  `move_tolerance` of the die's own size)

**The same roll reported twice.** With `require_throw`, a reading that was never preceded by
actual motion and reads identically to the last one is marked `stale`, and says so. Display
modes ignore it; anything that counts rolls must not count it twice.

**A frozen or replayed feed.** Two captures from a real sensor are never identical — noise
alone guarantees it. Identical captures in a row therefore mean the feed is frozen or
looped, not that the dice are lying still, and that is a fault. (This compares the raw
frames. The downscaled ones the motion detector uses go identical on any quiet table, and
checking there called every honest roll a fake.) The check is skipped on sources that repeat
by design — the folder simulator, and pushed frames.

**A covered lens.** Brightness collapsing to a fraction of the reading frame's is a fault.

**A camera that drops out mid-hold.** Recorded as a fault rather than crashing and losing
the roll.

## What it does not catch

- Anything done **before** the dice settle: a loaded die, a controlled throw, a die dropped
  in by hand rather than thrown. DiceCore reads what lands; it does not know how it got
  there. (`require_throw` only proves *something* moved, not that it was thrown fairly.)
- A die swapped for an identical-looking one showing the same face.
- Tampering under a hand that never leaves: if the tray is covered for the whole hold and
  the dice are unchanged afterwards, the reach is recorded but the reading stands.
- Anything at all once the hold window closes. `hold_s` is how long the promise lasts.
- Anything after the next throw begins: that roll is marked `superseded`, and rightly so.
- Someone with access to the Pi, the camera or the config.

## Settings

**Detection → Fair play** in the web UI, or `guard` in the config file.

| Setting | Default | What it does |
|---|---|---|
| `enabled` | `true` | Watch the tray after a reading |
| `policy` | `flag` | `off`, `flag` (report and mark), `void` (discard a disturbed roll) |
| `hold_s` | `2.0` | How long hands must stay out of the tray |
| `interval_s` | `0.15` | How often to look during the hold |
| `motion_threshold` | `2.0` | Frame difference (0–255) that counts as something happening |
| `hand_area_frac` | `0.05` | A change this large a fraction of the frame reads as a hand |
| `move_tolerance` | `0.4` | How far a die may drift, as a fraction of its own size |
| `void_on_touch` | `false` | Under `void`, void even when the dice did not change |
| `require_throw` | `true` | Mark a reading nothing was thrown for as `stale` |
| `freeze_frames` | `6` | Identical captures in a row that mean a frozen feed |
| `dark_fraction` | `0.35` | Brightness below this fraction of the reading frame is a covered lens |

### Which policy

- **`flag`** (default) for a game night. Everyone gets their number; the log says what
  happened. Nothing is ever taken away from someone who reached for the salt.
- **`void`** for a tournament table or a bot that pays out. A changed reading produces no
  number at all. Add `void_on_touch` where nothing may enter the tray, and expect to explain
  the rule to people before they learn it the hard way.
- **`off`** when DiceCore is a display and nobody is competing.

### The cost, and why there is almost none

Watching does not delay the number. `GET /api/v1/roll` answers as soon as the dice are read
— about a fifth of a second after they stop — with `verdict: "pending"`, and the hold window
runs on its own thread behind it. The verdict lands on `/api/v1/state` and on the websocket
a couple of seconds later.

```bash
curl http://dicecore.local:8099/api/v1/roll              # number now, verdict "pending"
curl http://dicecore.local:8099/api/v1/state             # the same roll, with its verdict
curl "http://dicecore.local:8099/api/v1/roll?verify=1"   # or wait for it up front
```

**You never have to wait to throw again.** Starting a new roll cancels the previous watch
and marks that roll `superseded`; it does not void it. `hold_s` is how long the tray must be
left alone for a *clean* verdict, not a lockout.

The websocket does this for you: every roll arrives twice, first as `pending` and then with
its verdict. A scoreboard renders the first; a bot that must not honour a tampered roll acts
on the second.

## Reading the record

Every verified roll carries an `integrity` block:

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

- `severity` is `info` (a note), `warn` (worth showing) or `fault` (voids under `void`).
- Each kind is recorded **once** per roll: a hand held over the tray for two seconds is one
  reach, not forty.
- `seal` identifies this exact roll — the frame plus what was read from it. Log it, and a
  number can later be pointed back at the picture that produced it.
- `settled_check` is false only when the second reading could not be taken.
