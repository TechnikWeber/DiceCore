# Changelog

Notable changes, newest first. Dates are the day the work landed.

## 0.2.0 (2026-09-02)

Fair play: reading the dice was only half of it. Between the camera and the game a hand can
turn a die over, so the tray is now watched after the number is read.

### Added
- **The tray is watched after the reading.** For `hold_s` seconds any movement is recorded,
  and at the end the dice are read again and compared with what was published. A hand
  reaching in is flagged; a changed reading voids the roll under `policy=void`.
- Caught: a die turned over, added, palmed or nudged; the same roll reported twice with
  nothing thrown (`stale`); a frozen or replayed feed; a covered lens; a camera that drops
  out mid-hold.
- `verdict` and `usable` on every result, plus an `integrity` record of what was seen and a
  `seal` identifying the exact frame and reading.
- `GET /api/v1/roll?verify=0` and `POST /api/v1/verify` for callers that want the number
  before the verdict; the websocket sends every roll twice, `pending` then judged.
- **Detection → Fair play** in the UI, and the verdict shown next to the number.
- `docs/ANTI-CHEAT.md`, which states the limits as plainly as the features: this is tamper
  evidence, not tamper proof, and it knows nothing about a loaded die.
- 110 tests in total, none of which need a camera.

### Known gaps
- Fair-play thresholds come from synthetic scenes; `hand_area_frac` and `motion_threshold`
  need checking against a real hand over a real tray.
- Nothing protects against a loaded die, a controlled throw, or anyone with access to the
  camera. That is stated in `docs/ANTI-CHEAT.md` rather than implied away.

## 0.1.0 (2026-09-01)

The first skeleton. Everything below works on a laptop with no camera; nothing has been run
on a real dice tower yet.

### Added
- **Reading**: the classic engine — segments dice against the tray and counts pips, with a
  confidence derived from how uniform the pips are. Polyhedral dice are located and reported
  as unread rather than guessed at.
- **Capture**: `picamera2`, `rpicam-still`, `v4l2`, `folder` (simulator) and `push` sources
  behind one interface, plus settle detection so a frame is never read mid-tumble.
- **Engines are interchangeable**: `classic`, `model` (ONNX), `remote` (another DiceCore
  node does the reading), and `auto`.
- **CSI camera module selection** ported from YonderRC: Arducam IMX519 / 64MP / Owlsight /
  Pivariety and the official modules, written into `config.txt` from the web UI, including
  the IMX519 tuning file whose absence looks like a soft lens.
- **Dataset and label loop**: named sets, a roll stored with the engine's guesses pre-filled,
  correct-and-confirm in the browser, per-face counts and an engine-agreement measure.
- **Training** as a watchable background job: a small rotation-invariant classifier over
  64×64 die crops, exported to ONNX, with per-class validation splitting.
- **API**: `/api/v1/roll`, `/state`, `/detect`, `/frame`, `/health` and a websocket event
  stream, documented in `docs/API.md` as a stable contract.
- **Web UI**: one HTML file and one JS file, no build step — Roll, Camera, Detection,
  Training, API and System.
- **CLI**: `serve`, `roll`, `doctor`, `synth`, `sets`, `train`, `camera-module`.
- **Synthetic dice** for tests and for a first run without hardware, including polyhedral
  silhouettes with a numeral on the top face.
- 62 tests, none of which need a camera.

### Known gaps
- No trained model exists yet, so numerals are not read.
- Overlapping and cocked dice are not handled.
- Every hardware path (picamera2, rpicam, config.txt) is written but unverified on a Pi.

