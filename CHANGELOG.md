# Changelog

Notable changes, newest first. Dates are the day the work landed.

## 0.6.0 (2026-09-02)

A second board, an extended sheet, and chips that belong to a player rather than to a turn.

### Added
- **Farkle has a board**, and it is deliberately the opposite shape to Kniffel: throw as
  often as you dare, set aside the dice that score — they leave the tray, so the next throw
  really does have fewer dice in it — then bank or throw again. A throw with nothing in it
  loses the whole turn; six dice set aside brings the whole hand back.
- Setting aside a die that scores nothing is **refused**, because carrying one along would
  quietly cost a throw's worth of dice.
- **Kniffel Extreme**: six dice and eighteen boxes — five and six of a kind, two pairs and
  three pairs, a big full house of three and three, a straight from one to six. The bonus
  asks for 84 and pays 50. A defined house sheet, stated as such, not a boxed product.
- A scorecard is now a **sheet in a table**, so a third variant is an entry rather than a
  file — and the browser draws whatever sheet the server describes.
- `POST /api/v1/game/aside` and `/api/v1/game/bank`.

### Changed
- **Chips are per game, not per turn.** Three chips means three for the evening, so
  spending one is a decision; refilling them every turn left only a button. A new game
  hands them back.
- A game with no throw limit says a chip would buy nothing, rather than "no chips left" —
  the second sends someone looking for more.

## 0.5.0 (2026-09-02)

DiceCore stops only reading and starts playing. Two front doors, one service: `/` is the
game screen for the television at the table, `/setup` is everything else.

### Added
- **A game screen** at `/`: the headline in large letters, the dice drawn (a six-sider as
  pips), the throw counter, the scorecard, the last turns. Opening it is what starts
  DiceCore watching the tray.
- **Turns**, for the games where one throw is not the whole story. Kniffel is three throws
  with dice kept in between; the counter runs down, and a throw only counts when the dice
  actually changed.
- **Holds, observed rather than enforced.** DiceCore notices which dice did not move and
  shows those as kept; tap one in the browser to correct it. Nothing depends on the guess:
  what is scored is what is on the tray.
- **Chips** — up to three a turn, a house rule rather than part of the game — buy one more
  throw once the ordinary ones are gone, and cannot be spent while any remain.
- **Two GPIO buttons**, chip and end-turn, calling exactly the endpoints the browser
  buttons do. Wire each between the pin and ground; `-1` leaves one out.
- **A Kniffel scorecard** in the browser: every open category shows what it would score
  right now, tapping books it and hands the tower on. Several players, upper bonus, and a
  crossed-out box that has to be given up deliberately.
- **The panel carries the turn too**: `2/3` and a dot per chip, and a caption that says
  what you may do next — *throw again*, *chip or book*, *turn over*.
- `GET /api/v1/game` and five POSTs, all versioned, so a play screen can be written by
  somebody else. The websocket carries the game state alongside every roll.
- **A zero on a 0–9 ten-sider can be worth nothing instead of ten**, for the tables whose
  house rules say so. Ten remains the default.
- `docs/PLAYING.md`.
- 214 tests.

### Changed
- The `output` package is now `panel`, because it listens as well as speaks. The config
  section moved with it, and an existing config's `output` block is carried over rather
  than silently replaced by defaults.
- The setup page moved from `/` to `/setup`.

### Fixed
- The play screen showed the headline of whatever the camera had looked at last, which in a
  turn with no throws left is a different set of dice than the ones on the board. A turn
  keeps its own reading now.
- Settings loaded from JSON only descended one level, so `panel.display.kind` came back as
  a plain dict. (Fixed in 0.4.0's cycle; the nesting got deeper here and would have hidden
  it again.)

## 0.4.0 (2026-09-02)

Game modes. DiceCore reads dice; a mode reads the *result* — which is the difference between
a project about one game and one that is useful at any table.

### Added
- **Fourteen game modes**, as a table plus one pure function each: plain pips, pips with
  ten-siders, the polyhedral set, a dice pool counting successes, best-or-worst of several,
  exploding dice, roll-under-a-target, Kniffel, Farkle, Backgammon, Mäxchen, a single die
  shown large, a fairness test, and a build-your-own for everything else.
- **A dice pool covers a family, not a game**: Warhammer, Shadowrun, World of Darkness and
  Blades in the Dark are one mode with two settings between them.
- **A fairness test**: a chi-square goodness-of-fit against a flat distribution, with the
  critical values written out rather than pulled from a statistics stack. Three answers —
  not enough data, nothing unusual, unusual — and deliberately no "fair", because the test
  cannot show that.
- **Exploding rolls keep their state between throws** and the display says `16…` while one
  is still open.
- `reading` on every result — headline, value and the mode's own detail — and the screen
  shows the headline, so a Kniffel reads "Full house" rather than "19".
- `GET /api/v1/modes`, and `?mode=` on a roll to read it as another game **without changing
  the configured one**: a bot counting successes and a screen showing a total can share one
  tray, each with its own memory.
- **Ten-sided dice can be printed 0–9 or 1–10**, set once for the dice you own — it decides
  the labels a model is trained on. Whether a zero counts as ten is separately a per-mode
  setting, because that one genuinely is the game's business.
- The web UI builds a mode's settings form from the mode's own defaults, so the next game is
  a table entry and no UI work.
- `docs/GAME-MODES.md`.
- 179 tests; the scoring rules are pure functions, so every game is testable on its own.

### Fixed
- **`value == 0` meant two different things**: "could not be read" and "a d10 showing zero".
  A ten-sider's zero face was being dropped out of every sum. `Die.unread` now says which is
  which, and the dataset records an unread die as *no guess* rather than as a zero.

## 0.3.0 (2026-09-02)

A number nobody can see is not much use at a table, and the fair-play watch was making
everyone wait for it. Both fixed.

### Added
- **A screen over the tower**: ST7789 and ILI9341 (SPI, colour) and SSD1306 (I²C or SPI,
  monochrome), in every size they are sold in. One renderer for all of them, measured to
  fit the panel rather than assuming a shape.
- **Two lamps and a buzzer** on three GPIOs: green means throw, red means hands off, and
  the buzzer marks the number arriving and your turn coming round. Any pin set to `-1` is
  simply left out.
- A natural maximum gets a short animation and a three-note beep; a natural 1 gets a flat
  screen and one long note. A die that could not be read never celebrates.
- **Both are previewed in the browser** — the panel image is rendered whether or not
  hardware is attached, and the lamps are shown lit. **Screen & lamps → Run through the
  phases** walks the whole sequence so wiring can be checked without throwing anything.
- `docs/DISPLAYS.md` with panels, pins and wiring tables.
- 134 tests, none of which need a camera, a screen or a GPIO header.

### Changed
- **The number no longer waits for the verdict.** `GET /api/v1/roll` answers as soon as the
  dice are read (~0.2 s after they stop); the hold window runs in the background and the
  verdict lands on `/api/v1/state` and the websocket. `?verify=1` waits for it, as the old
  default did.
- **Throwing again immediately is normal play**: a new read cancels the previous roll's
  watch and marks it `superseded` instead of voiding it.

### Fixed
- Nested settings (`output.display.kind`) came back from the config file as plain dicts —
  the loader only descended one level.

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

