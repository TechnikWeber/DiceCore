# CLAUDE.md — DiceCore

Guidance for Claude (and humans) working in this repository.

## What this is
A camera over the landing area of a dice tower, a Raspberry Pi, and an API that says what
was rolled. **`docs/CONCEPT.md` is the reference for the goal — read it before adding
features, and change it in the same commit if a change contradicts it.**

Owner: Philipp Weber · GitHub: TechnikWeber/DiceCore

## Layout (src layout, Python ≥ 3.10)
- `src/dicecore/dice.py` — the vocabulary: `Die`, `Box`, `RollResult`, `Frame`, die kinds.
  Pure data, no dependencies. Everything else speaks this.
- `src/dicecore/config.py` — one JSON file, one dataclass tree. Unknown keys survive a round
  trip; a broken file degrades to defaults with a complaint.
- `src/dicecore/capture/` — `base` (interface) plus `folder` (sim), `v4l2`, `rpicam`,
  `picamera2_src`, `push`, and `settle` (wait for the dice to stop).
- `src/dicecore/engine/` — `classic` (pips, no training), `model` (ONNX), `remote` (another
  node reads), `geometry` (every decision that can be made on numbers instead of pixels).
- `src/dicecore/dataset/` — labelled rolls on disk: one JPEG plus one JSON per frame.
- `src/dicecore/training/` — `data` (crops, readiness, no torch), `trainer` (torch),
  `job` (a watchable background run).
- `src/dicecore/system/` — `boot_config` (CSI modules in config.txt), `diagnostics`.
- `src/dicecore/modes/` — game modes: `catalogue` (the table), `scoring` (pure rules, one
  function per game), `fairness` (the chi-square tally), and `interpret()` in `__init__`.
- `src/dicecore/integrity.py` — fair play decided on numbers: comparing two readings,
  classifying events, turning them into a verdict. No pixels.
- `src/dicecore/guard.py` — the hold window after a reading: turns frames into events.
- `src/dicecore/reader.py` — capture → settle → engine → guard. The single owner of the
  camera, and the only place that knows about the *previous* roll (staleness, replay).
- `src/dicecore/output/` — what a person sees: `state` (one `Presentation` for every output,
  pure), `render` (PIL, one renderer for every panel), `displays` (ST7789 / ILI9341 /
  SSD1306 via luma, plus an always-on PNG preview), `signals` (LEDs and buzzer via gpiozero),
  and the hub that fans out on its own thread.
- `src/dicecore/server/` — FastAPI, plus `web/` (one HTML, one JS, one CSS; no build step).
- `src/dicecore/synth.py` — synthetic dice, for tests and for a first run without hardware.

## Commands
```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[vision,server,dev]'
.venv/bin/pytest                     # must stay green; no hardware needed
.venv/bin/ruff check src tests
.venv/bin/dicecore synth --count 20  # frames for the simulator
.venv/bin/dicecore serve             # → http://localhost:8099/
```

## Conventions / gotchas (read before editing)

- **Sim-first.** Every capture source and every engine has an implementation that runs on a
  laptop. Hardware paths are only verifiable on the Pi, so everything else must be verifiable
  without one. A new feature that can only be tested on hardware is a design smell.
- **Dependencies are extras, and the base package has none.** The agent shape (capture a
  JPEG, POST it elsewhere) has to install on an **ARMv6 Pi Zero v1**, where there is no
  OpenCV, no onnxruntime and no PyTorch. `import numpy` at module scope in the wrong file
  breaks that. Use the `require_numpy` / `require_cv2` helpers or a function-level import,
  and fail with a sentence that says what to install.
- **Errors are prose, and they travel.** `CaptureError`/`EngineError` messages are printed
  verbatim by the CLI and the web UI. "No camera bound to dtoverlay=imx519" is a repair
  instruction; "read failed" is not.
- **A die that could not be read is `value=0`, never a guess.** `notation` prints it as `?`.
  Guessing a number that looks confident is the worst failure this project has, because a
  consumer will add it up.
- **`server/app.py` deliberately has no `from __future__ import annotations`.** FastAPI
  resolves parameter annotations against *module* globals, and the FastAPI symbols are
  imported inside `create_app` so the module stays importable without FastAPI. With
  postponed annotations, `request: Request` silently becomes a missing query parameter and
  every POST body is rejected with a 422. `tests/test_api.py` guards this.
- **`prepare_crop` has exactly one implementation**, shared by training and inference. If the
  two ever crop differently the model degrades quietly instead of failing — the worst kind of
  bug.
- **A reach is suspicious, a changed reading is disqualifying.** Do not "improve" the guard
  by voiding on motion alone: someone reaching past the tower for their drink would lose a
  legitimate roll, and that is worse than the cheating it would prevent. The re-read is what
  decides.
- **Frozen-feed detection compares raw frames, never the prepared ones.** After the downscale
  and blur the motion detector uses, two genuinely different captures of a still tray come
  out identical all the time — checking there called every quiet table a fake. And it only
  runs on `source.is_live`; the folder simulator repeats frames by design.
- **The number goes out before the verdict does.** `read()` returns as soon as the dice are
  read and the hold window runs on a thread. Making the caller wait put two seconds between
  the dice landing and anyone seeing a number, which is the opposite of what a dice tower is
  for. A new read cancels the previous watch and marks that roll `superseded` — throwing
  again immediately is normal play and must never void anything.
- **`Die.unread` is not `value == 0`.** A d10 printed 0–9 has a zero face; filtering on
  `value == 0` dropped it out of every sum. Unread means no value *and* no confidence.
- **A mode is data.** New game → an entry in `catalogue.py` and a function in `scoring.py`.
  The web UI builds its settings form from the mode's own `defaults`, so a new mode needs no
  UI work at all. If a mode needs a change to the reader, the design is wrong.
- **A mode reads, it does not rule.** No modifiers, no turn order, no character sheets. The
  moment a mode needs to know something DiceCore cannot see on the tray, it belongs in the
  consuming game instead.
- **Modes with memory keep it per mode** (`Reader.mode_sessions`). Two consumers may read
  one tray differently — a screen in `normal` and a bot in `pool` are both right, and
  neither may reset the other's fairness tally.
- **One `Presentation` drives every output.** The screen and the lamps must not be able to
  disagree about whose turn it is, so both are derived from the same value rather than each
  interpreting the reader's events. `presentation.go` is what the green lamp means.
- **An output must never be able to break a reading.** A panel that will not start, a pin
  that is taken, a screen that stops answering: all reported through the UI, none fatal.
  The hub runs on its own thread precisely so a slow SPI write cannot delay a roll.
- **Only confirmed dice are trained on.** Training on the engine's own guesses teaches it its
  own mistakes.
- **Rotation augmentation is not optional.** Dice land in any orientation; a model trained
  without full 360° rotation learns the orientation of one tower. 6 vs 9 survives it because
  real dice underline them.
- **Never name a module after a stdlib module.** `types.py` inside the package shadows
  `types` for anything run from that directory; that is why the vocabulary lives in
  `dice.py`.
- **config.txt is the file that decides whether the Pi boots.** Competing lines are commented
  out, never deleted; our block is fenced and applying twice is a no-op; a custom overlay name
  is validated before it is written. All of it is pure text manipulation so
  `tests/test_boot_config.py` can pin it down.
- **The UI has no build step, and keep it that way.** The service reads the HTML per request.
  That is what makes "git pull && systemctl restart" a complete update on a Pi.
- **Every UI tab is a URL** (`…/#training`), so a link into a panel works and a reload keeps
  the tab.
- `/api/v1/…` is a contract other repos depend on: additive changes only. `/api/setup/…` is
  the UI's own back end and may change freely.

## Testing
The suite renders its own dice (`synth.py`) so recognition is genuinely exercised without
committing photographs. Synthetic scenes are **not** training data — a model trained on them
learns to read drawings. Real data comes from the label loop.

Tests that need a stack that may be missing use `pytest.importorskip`, so the suite still
runs on a Pi with nothing installed.

## Style
Comments explain **why**, especially where the obvious implementation is wrong (frame
bucketing in `sort_reading_order`, per-die thresholding in `_count_pips`, padding before
rotation in `synth`). Do not add comments that restate the code.
