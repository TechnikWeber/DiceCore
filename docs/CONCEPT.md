**English** · [Deutsch](CONCEPT.de.md)

# DiceCore — Concept

The reference for *what this is meant to be*. Read this before adding features; if a
change contradicts something here, change this document in the same commit.

## Goal

A camera looks down on the landing area of a dice tower (or any tray, or a bare table).
DiceCore turns what lands there into **structured data**: how many dice, of which kind,
showing which value, and what they add up to. That data is available as a number on a
screen, as an HTTP/JSON API, as a websocket event stream, and — later — straight into a
Discord bot or a game.

DiceCore is the **engine other projects embed**, not an application. Everything a
consumer needs is one HTTP call or one Python import away, and the vision internals stay
replaceable.

Three properties decide every design question here:

1. **Sim-first.** The whole system runs on a laptop with no camera at all — simulated dice
   are the default source, and a folder of JPEGs replays real ones. Hardware paths are only verifiable on the Pi, so everything else must be
   verifiable without one.
2. **The Pi may be weak.** A Pi Zero (v1) is ARMv6 — no PyTorch, no onnxruntime, no
   modern OpenCV wheels. So capture and recognition must be **separable**: the Pi grabs
   frames, something else may do the thinking. See *Deployment shapes*.
3. **The user decides how smart it gets.** Classic image processing and a trained model
   are two interchangeable engines behind one interface, chosen in the UI — not a
   migration from one to the other.

## What makes this hard

Counting pips on a d6 lying on a clean tray is a solved exercise. The real problems are:

- **Polyhedral dice show more than one number.** On a d20 the camera sees the top face
  *and* the surrounding faces at an angle. Reading "the biggest, most centred, most
  head-on numeral" is the actual task — not OCR of everything visible.
- **Numerals are ambiguous.** 6 vs 9 needs the underline convention (or the die's
  orientation); 1 vs 7 varies by manufacturer.
- **Dice differ wildly.** Colour, translucency, metallic, swirled, inked vs raw. A model
  trained on one set generalises badly to another — which is exactly why the training
  workflow has to be so easy that retraining for a new set of dice is a five-minute job,
  not a project.
- **The tower moves and the light changes.** Fixed geometry cannot be assumed forever;
  the tray region and the scale (mm per pixel) are configuration, not constants.
- **Knowing when the roll is over.** A frame grabbed mid-tumble is worthless. Settling
  detection (frame differencing until motion stops, then N stable frames) is part of the
  pipeline, not an afterthought.
- **Knowing the number is still true.** Reading the dice is only half of it: between the
  camera and the game, a hand can turn a die over. Watching the tray afterwards is part of
  the pipeline for the same reason settling is — see *Fair play*.

## Architecture

```
        ┌──────────────┐   frames    ┌──────────────┐   RollResult   ┌────────────┐
        │   Capture    │ ──────────► │    Engine    │ ─────────────► │  Outputs   │
        │              │             │              │                │            │
        │ picamera2    │             │ classic      │                │ HTTP/JSON  │
        │ rpicam-still │             │ model (onnx) │                │ WebSocket  │
        │ v4l2/OpenCV  │             │ remote       │                │ Web UI     │
        │ folder (sim) │             │              │                │ Discord…   │
        └──────────────┘             └──────────────┘                └────────────┘
                │                            ▲
                │        ┌──────────────┐    │
                └──────► │   Dataset    │────┘  labelled frames → training → model
                         └──────────────┘
```

Every arrow is a plain Python interface with a simulated implementation, and every box is
swappable through configuration alone.

### Capture

`FrameSource.grab() -> Frame`. Implementations: `picamera2` (Pi, CSI), `rpicam` (shells out
to `rpicam-still`, the fallback for Pis where picamera2 is a pain), `v4l2` (USB cameras via
OpenCV), `sim` (drawn dice — the default), `folder` (a directory of images, replayed), `push` (frames
arriving through the API from another DiceCore node).

**CSI camera modules are configuration, not luck.** A Pi only binds a sensor the firmware
knows: the four official modules are found by `camera_auto_detect=1`, everything else —
Arducam IMX519 16MP, 64MP Hawkeye, OV64A40 Owlsight, Pivariety — needs
`camera_auto_detect=0` plus an explicit `dtoverlay=` in `/boot/firmware/config.txt` and a
reboot. Picking that module belongs in the web UI, never in an SSH session. The logic is
ported from YonderRC (`packages/vehicle/src/system/bootConfig.ts`), including the hard-won
detail that Raspberry Pi's own `imx519.json` tuning file has no autofocus algorithm, so the
IMX519 needs the shipped `imx519-af.json` or its lens simply never moves.

### Engine

`Engine.read(frame) -> RollResult`. Three implementations:

- **`classic`** — no training, no dependencies beyond OpenCV. Segments dice against the
  tray, counts pips per die by blob detection. Honest scope: pipped dice (d6, and pipped
  d10 faces), good light, contrasting tray. This is what makes the project useful on day
  one and it stays useful as the fallback when no model is loaded.
- **`model`** — a trained network. Two stages, deliberately: **(a)** find the dice
  (segmentation or a small detector), **(b)** classify each cropped die into
  `(die_type, value)`. Two stages instead of one end-to-end detector because crops are
  cheap to label, the classifier is small enough for a Pi 4/5, and adding a new set of
  dice means retraining only stage (b).
- **`remote`** — forwards the frame to another DiceCore instance's `/api/v1/detect` and
  returns its answer. This is what makes an ARMv6 Zero useful: the Pi captures, a PC or a
  Pi 5 reads. The API is identical either way, so a consumer never knows the difference.

### Fair play

The tray does not stop mattering the moment it has been read. For `hold_s` afterwards it
stays watched, and at the end the dice are read again and compared with what was published.
A hand reaching in is *suspicious*; a **changed reading** is disqualifying. That split is
the whole design: someone reaching past the tower for their drink must not lose a
legitimate roll, and a die turned over between two frames must not slip through.

The rules live in `integrity.py` and are decided on numbers, not pixels, so what counts as
cheating is testable. `guard.py` only turns frames into events.

**It is tamper evidence, not tamper proof**, and DiceCore never claims a roll was fair — it
says what happened and lets the consumer decide. Anyone who controls the camera defeats it,
which is why a frozen feed and a covered lens are themselves faults rather than silence.
[docs/ANTI-CHEAT.md](ANTI-CHEAT.md) states the limits in full; they belong in the
documentation, not in a footnote, because a fairness feature that overpromises is worse
than none.

### Deployment shapes

| Shape | Capture | Engine | For |
|---|---|---|---|
| **All-in-one** | Pi 4 / Pi 5 | `classic` or `model` locally | The normal case |
| **Split** | Pi Zero / Pi 3 | `remote` → PC or Pi 5 | Weak Pi, or a big model |
| **Agent only** | Pi Zero | none — pushes frames | Absolute minimum on the Pi |
| **Desk** | `sim` / `folder` | any | Development, training, tests |

### Dataset and training

The training data comes from the thing itself: **you roll, DiceCore guesses, you confirm
or correct.** Every confirmed roll is a labelled sample. That loop lives entirely in the
web UI — no command line, no manual labelling tool, no folder juggling:

1. Pick or create a **set** ("my black d20s", "the translucent café set").
2. Roll. The frame is captured, dice are located, each one gets a guess.
3. Tap a wrong value, type the right one. Confirm.
4. At any point: **Train**. Progress, loss and accuracy stream into the page; the result is
   an ONNX file that the `model` engine picks up.

Storage is deliberately boring: one directory per session, the original frames as JPEG
next to one JSON per frame holding the dice boxes, types and values, plus the camera and
lighting metadata. Copyable, inspectable, and readable by any other tool.

Training itself needs PyTorch, so it runs where PyTorch runs — the PC. A Pi that cannot
train can still *collect* (dataset stays on the Pi, or is pushed to the trainer) and can
still *run* the exported model if it is a Pi 4/5. The UI states plainly which of those
this machine can do rather than failing halfway through.

### Game modes

Reading the dice and reading the *result* are two jobs. A mode says which dice may appear,
how the faces become an answer, and what belongs on a screen in big letters — as a table
entry plus a pure function, never as a change to the reader.

This is what keeps the project from being about one game. The camera does not care whether
five sixes are thirty points or a Kniffel; the scoring does not care how the sixes were
recognised. A mode is also the cheapest accuracy setting there is, because naming the dice a
game uses narrows what the engine has to consider.

A mode is not a rules engine: DiceCore does not know your modifier, whose turn it is, or
what you rolled for. See [docs/GAME-MODES.md](GAME-MODES.md).

### Playing, not only reading

Some games are not one throw. Kniffel is three, with dice kept in between, so there is a
turn machine (`play/turns.py`), a scorecard (`play/kniffel.py`) and a live game the browser
and the panel both render (`play/session.py`).

**Holds are observed, not enforced.** A camera cannot stop a hand, and nothing here depends
on the guess being right: what is scored is what is on the tray. The holds only tell the
player what is being kept, and the browser can correct them.

The game lives on the *server*, not in the browser — so the screen over the tower can say
"throw 2 of 3" too, a closed tab loses nothing, and a phone at the other end of the table
sees the same game rather than its own copy.

`/` is the game screen and `/setup` is the workshop. Two front doors, one service; see
[docs/PLAYING.md](PLAYING.md).

### Several DiceCores, one game

A table is not necessarily a room. One instance opens a table, others join it over the
network, and one game runs across all of them turn by turn — each player throwing on their
own tray, with their own camera or their own simulator.

**The host owns the game; guests own nothing.** They mirror it and *ask*. Nothing merges and
no conflict is resolved, because there is exactly one answer to "whose turn is it" — which is
the difficulty of a turn-based game played in three rooms at once. The turn rule is enforced
at the host, never at the button. See [docs/ONLINE.md](ONLINE.md).

## Outputs and modes

The same `RollResult` is served through every output; a mode only chooses what is
emphasised, never a different pipeline.

- **Display** — the number, big, in the browser. Total, or per die.
- **API** — `GET /api/v1/roll` (read now), `GET /api/v1/state` (last result), websocket
  `/api/v1/events` (a result pushed as soon as the dice settle, then again with its
  fair-play verdict).
- **Notation** — a dice-notation summary for consumers that want text: `2d20+1d6 → 14, 3, 5`.
- **Reading** — what the active mode made of it: a headline for a screen, a value for
  arithmetic, and the mode's own detail.
- **Consumers** — a Discord bot, a game, a scoreboard. They live in their own repos and
  depend on this API, not on this code. That direction is the whole point.
- **Outbound** — the same roll pushed the other way: a Discord webhook, an Avrae user
  variable an alias reads back, or JSON to any URL. Nothing about a roll changes; only who
  starts the conversation. See [docs/AVRAE.md](AVRAE.md).

## Non-goals

- Not a dice *roller* — no RNG, no rules engine, no character sheets. DiceCore reads
  physical dice, full stop.
- Not a general OCR project.
- Not a cloud service. It runs on your network; nothing leaves it.
- Not a fairness/casino-grade auditing tool. It reports interference with a *settled* tray;
  it knows nothing about loaded dice or a controlled throw. Detecting those is a statistics
  problem a consumer can solve on top of this data.

## Roadmap

1. **Skeleton** — config, capture (sim + Pi), classic d6 engine, API, web UI, camera module
   selection. *You can roll and see a number.*
2. **Dataset + training loop** — set management, confirm/correct labelling, training job
   with live progress, ONNX export, `model` engine. *You can teach it your dice.*
3. **Polyhedral quality** — top-face selection, 6/9 disambiguation, mixed-dice rolls,
   settling and fair-play thresholds tuned on real footage.
4. **Consumers** — reference Discord bot and a minimal game integration, each in its own
   repo, to prove the API is actually embeddable.
