# Changelog

Notable changes, newest first. Dates are the day the work landed.

## 0.14.0 (2026-09-02)

### Added
- **Playing against other DiceCores.** One instance opens a table, the others join it over
  the network, and one game runs across all of them turn by turn — every roll appearing on
  every screen as it lands. Each player throws on **their own** tray, their own camera or
  their own simulator, so nobody has to share a tower. `Play online` in the lobby, the
  address the host screen shows, done. Works on a LAN, over Tailscale, over anything where
  one machine can open a socket to another; [docs/ONLINE.md](docs/ONLINE.md) has the detail.
- **Sim dice: a capture source with no recognition in front of it.** Pick `sim` under
  *Setup → Camera* and a `Throw` button appears on the game screen. It is not a random
  number generator with a scoreboard attached: it **draws the dice and reads the picture
  back through the real engine**, so the settling, the modes, the boards, the panel and the
  screens all behave exactly as they do with a camera — and a bug in any of them shows up on
  a laptop rather than only on hardware. A game night with no tower, no camera and no dice
  at all now plays.
- Every combination works and none is a special case: everyone round one screen with a real
  tower, everyone round one screen with none, four people in four rooms with towers, four
  with none, or a mix of the two in the same game.
- `POST /api/v1/throw`, `GET /api/v1/table`, `POST /api/v1/table/{host,close,join,leave,act}`
  and the guest websocket at `/api/v1/table`, all versioned and documented.
- The host screen lists **every address it can actually be reached at**, best first — the
  LAN address, the Tailscale `100.x` one, and the `.local` name — because `localhost` is the
  one address guaranteed not to work for the other players.

### Fixed
- **The host did not broadcast its own moves.** Guests only ever heard about rolls, so every
  remote screen sat one move behind — and, worse, a guest whose mirror still said it was
  somebody else's turn did not send its dice up at all. Persisting and broadcasting now both
  hang off the session's change hook, which is a list rather than a single callback.
- **A host could throw for a guest.** The play screen treated "not away" as "my turn", so the
  hosting instance offered a `Throw` button during a remote player's turn. The host now
  plays only the seats that are actually at its own screen.
- **The simulator was never stale.** Staleness was inferred from motion, and a simulator does
  not move — so polling `/roll` against one would have spent a Kniffel throw per poll. It now
  reports the fact directly: it knows exactly whether anybody has thrown since it was read.
- The dice pool came from the configured mode rather than the running game, so a game started
  from the lobby while the API was left on another mode threw the wrong number of dice.
- The table address reported the configured port, not the port the service was started on.
- `Join` answered "joining…" before it had tried, so a typo left the screen spinning at an
  address that would never answer. It now waits out the first attempt, reports what happened,
  and only keeps retrying an address that has worked at least once.
- The "Throw the dice" prompt printed its letters on top of each other: `letter-spacing` is
  inherited as an absolute length resolved where it was declared, and the headline's `-.03em`
  is `-5px` at 168px — which is half a glyph at 18px.
- `/api/v1/health` reported the version written out by hand in `app.py`, which had drifted a
  release behind the package. It comes from `__version__` now, and a test says so.
- An open scorecard box shows what it is worth to everyone at the table, not only to the
  player whose turn it is. Watching somebody decide is most of the game.

## 0.13.0 (2026-09-02)

### Added
- **A way in when there is no network.** Ported from YonderRC: after 45 seconds without a
  network the box opens its own, and a captive portal on port 80 pops the setup page open on
  a phone. Forty-five seconds rather than immediately, because a router rebooting takes a
  network away for twenty and a box that runs off with its own radio every time is worse
  than one that waits. A **Network** page scans, joins, sets the WiFi country and opens or
  closes the box's own network by hand.
- The hotspot is built with explicit `nmcli` calls rather than `nmcli device wifi hotspot`,
  which cannot produce an **open** network — and open is the point, since somebody who
  cannot reach the box cannot be told a password either. A failed join **reopens** it, so a
  wrong password never leaves a box unreachable.
- The page names the actual failure: "device is not available" means the radio is blocked
  because no WiFi country has ever been set, which is the most common reason a fresh Pi's
  hotspot never appears and a sentence nobody guesses.
- **Undo**, one step, for a booking, a bank or an ended turn. A misclick on a scorecard cost
  that box for the rest of the game, which is the most expensive mistake the interface
  allows and the easiest one to make.
- **"All correct"**: one button confirms every stored roll the engine read completely. Two
  hundred d20 faces was two hundred clicks, and that is the evening that decides how good
  the model gets. Rolls with a die the engine could not read are left for a person — those
  are the ones that need looking at.
- `docs/NETWORK.md`.

### Fixed
- **The auto-hotspot would have taken over a desktop's WiFi.** As first written it ran
  everywhere, so a development machine would have seized the adapter and started serving an
  access point the first time a router rebooted for longer than the grace period. It is now
  "on a Raspberry Pi only" by default, with "always" and "never" available.
- **The model pipeline had never been run once, and did not work.** `torch.onnx.export`
  needs `onnxscript`, which was missing from the `train` extra — so training completed and
  then failed at the one step that produces a model. Fixed, and the whole chain (train →
  export → load → read) now runs as a test: 98% validation accuracy on a synthetic set and
  9 of 10 dice read correctly from fresh frames.
- The ONNX export used the deprecated `dynamic_axes` form, and the modern `dynamic_shapes`
  is positional rather than keyed by input name — keying it by name falls through to the old
  path silently, which is why it was easy to get wrong.
- The training loop read its loss off a tensor that still carried a gradient.
- **"No dice found" now says why.** It counts what was rejected and by how much: *"1 object
  was rejected as too big — the largest filled 15% of the tray and the limit is 8%"*. A tray
  cropped tightly around the landing area, which the tray editor encourages, makes every die
  too big and used to say nothing at all.

## 0.12.1 (2026-09-02)

### Changed
- Fresh screenshots throughout: the game screen mid-Kniffel with three players and their
  colours, the lobby, the Training page with the sets-and-models explanation, the Avrae
  panel, and the workshop's Roll tab. Four of the five were still showing v0.1 interfaces
  that no longer exist.
- The status paragraph in both READMEs describes what the project is now rather than what
  it was at the first commit — and keeps saying the part that matters: nothing has run on a
  real tower yet.

## 0.12.0 (2026-09-02)

### Added
- **A model can be trained from several sets at once.** It was one set per model, which
  meant a friend's d20s and your own six-siders could never end up in the same model — the
  exact thing somebody would want. Pick the sets in the Train panel; the combined face
  counts update as you tick them.
- **Export and import a set** as a plain zip of the frames and the labels. Your friend
  collects a few hundred throws of his d20s on his own tower, sends you a file, and you
  train one model from his set and yours. It is also just a way to look at your own data
  with the tools you already have. An archive is never merged into an existing set, and a
  path inside one can never write outside it.
- **The second Avrae alias**, `!pr`, which is what most people actually want: it hands Avrae
  a die clamped to the number you threw (`1d20mi17ma17`), so the result goes through Avrae's
  own roller in Avrae's own format, bonuses and all.
- The setup page now explains, where the question gets asked: what a set is, what a model
  is, that a model is trained from sets rather than tied to one, and three worked examples —
  ordinary six-siders, Kniffel, and a roleplaying set.
- The Avrae panel now answers the question everybody asks first, plainly: **no, Avrae does
  not silently roll your number for whatever you type next**, and here is what it does
  instead.

## 0.11.0 (2026-09-02)

### Added
- **Rolls can be sent out**, which is the API in the other direction: instead of somebody
  asking DiceCore for a roll, DiceCore hands each finished one over.
- **Avrae**: each roll is written into an Avrae user variable, and a one-line alias in
  Discord reads it back. Verified against Avrae's own source rather than guessed —
  `POST /customizations/uvars/<name>` with an `Authorization` header, and `get_uvar()` in
  an alias. The setup page shows the alias with a copy button, already carrying the
  variable name you chose. **Avrae rolls its own dice and cannot be made to use yours**;
  what this does is put your number where an alias can reach it.
- **Discord**: a webhook message in a channel, so the table sees the physical roll land.
- **Anywhere else**: the same JSON the API returns, POSTed to a URL of yours.
- A **test button** that waits for the answer rather than firing and forgetting — finding
  out whether the token is right is the whole point, and "sent" is not that answer.
- `docs/AVRAE.md`.

All of it off by default. Sending happens once the fair-play verdict is in, so a voided roll
never reaches anybody's game; it runs on a thread; a failed delivery is recorded and not
retried; and the page can say whether a token is set but never what it is.

## 0.10.0 (2026-09-02)

### Added
- **A live view of the tray** at `/api/v1/stream.mjpg`, and a Camera button on the game
  screen, for playing with people who are not in the room. It never opens the camera a
  second time — it sends what the reader last captured — and it is **off until switched
  on**, because a continuous view of whatever a camera can see is the room's decision
  rather than a default.
- **The game screen celebrates too.** Until now only the little panel over the tower
  reacted, which is backwards: the big screen is the one everybody is looking at.
- A `near_max` celebration rule: nearly the best the dice on the tray could have shown.

### Fixed
- **Celebration thresholds did not scale with the dice.** A total of 18 is impossible with
  two six-siders, so a perfect throw of 2d6 never celebrated at all; and a dice pool
  celebrated at four successes, so three dice all succeeding — the best result there is —
  was never worth a sound. Both are proportional now.
- The training page still listed the dice without d2 and d3.

## 0.9.0 (2026-09-02)

### Added
- **One-line install**, the same shape as YonderRC's:
  `curl -fsSL …/provisioning/bootstrap.sh | bash`. It works out whether it is on a Pi or a
  desktop and installs what that machine can use — camera stack and a service on a Pi,
  PyTorch and no service on a desktop, the bare package on an ARMv6 Zero with a note to
  point it at another machine.
- **A button that installs PyTorch** (and the other optional halves) from the Training
  page, with pip's output streaming into it. The extra is picked from a fixed list rather
  than taken from the request — an endpoint that hands a user-supplied string to pip is
  remote code execution with a friendly label on it.
- **d3 and d2** join the vocabulary. A d3 is a real die even though most tables read one
  off a d6; that closes the roleplaying set. The exotic ones (d5, d7, d14, d16, d24, d30)
  are one line each and documented as such.
- Chips go up to **four** rather than three. The cap is a guard against a typo, not a rule,
  and the number a table plays with is the table's business.

## 0.8.1 (2026-09-02)

### Fixed
- The dataset picker under Training was an empty box when no set existed, which looks the
  same as a broken one. It now says so and switches off the buttons that need a set, and
  the panel explains what a set *is* rather than assuming.
- The training page says plainly that every die in the vocabulary can be learned — d4
  through d20, not only six-siders — and roughly how much rolling each one takes.

## 0.8.0 (2026-09-02)

A review pass that turned up more than it was meant to, plus the two things the game screen
was still missing.

### Fixed
- **The whole setup form was half empty.** Renaming `output` to `panel` in 0.5.0 left one
  stale path in the page's JavaScript; it threw, and every field after it — the game mode,
  settling, the players, the display, the lamps — silently never filled in. The form is now
  built in guarded sections, so one bad field can never blank the rest again.
- **The panel's end-turn button could throw a Kniffel turn away.** One press ended the turn
  without booking anything. Ending a turn is now refused wherever a decision is owed —
  book a category, bank the points — and only works where "done" is the whole story.
- **Saving a setting could take a running game away.** A mode change in the setup page
  turned a Kniffel with points on the card into an empty Farkle, mid-game, without a word.
  The lobby starts games; nothing else may end one.
- **"Which dice may appear" did nothing at all.** It is now what names a die the pip
  counter could not read, instead of a hardcoded d20.
- **A ten-sided die printed 1–10 could not be labelled as a 10.** The printing style is a
  setting, and it made its own labels illegal — which left the whole option useless for
  training.
- Removed `mode.restrict_kinds` and `play.enabled`: both were saved, shown, and read by
  nothing.

### Added
- **A tray you draw rather than type.** Drag a rectangle over the camera picture with a
  quarter-frame grid behind it; the four fractions follow. Four numbers typed into four
  boxes was a guess, and this is a measurement.
- **Colour detection**, optional and off by default: each die comes back named — red,
  blue, white, black — and the game screen draws them in their real colours. This is what a
  colour-dependent game (Qwixx, Sagrada, King of Tokyo) would be built on.
- **A game survives a restart.** The session is written to one small file after every move
  and read back when the service comes up. A file that cannot be read is a lost game, never
  a service that will not start.
- **What a zero on a 0–9 die is worth is now settable per game**, overriding the general
  answer — because that is genuinely a per-game house rule.
- Short explanations under every setting that names a thing nobody has met: what the
  classic engine is, what settling does, what each engine mode means, what the tray is for.
- The panel's end-turn button starts the configured game while in the lobby, which is the
  keyboard-free path: walk up, press one button, play.

## 0.7.0 (2026-09-02)

The game screen becomes a game screen. It had no lobby: it opened into whatever mode was
configured and started reading the tray, so a player was watching numbers change with no
idea what was going on.

### Added
- **A lobby.** Every mode as a tile, grouped into games, plain readers and workshop tools.
- **A setup wizard per game**, entirely by tapping: how many are playing (1–6, two already
  chosen), who (Player 1, Player 2 … each with its own colour, both editable and neither
  necessary), and the settings that game actually has — chips, target, threshold — as rows
  of buttons.
- **A colour per player**, running through the turn marker, the scorecard columns and the
  log. Tapping a swatch takes the next colour nobody else is using.
- **A result screen** with the standings and *Play again* with the same players.
- `POST /api/v1/game/start` and `/stop`; `running`, `colours` and each mode's `family` in
  the API.

### Changed
- **Nothing reads the tray until a game has been started.** The camera idles in the lobby,
  which is both what makes the screen comprehensible and what stops a Pi capturing all
  night for an empty table.
- The default player list is two rather than one.

### Fixed
- Cycling a player's colour walked blindly through the palette and could hand two players
  the same one, which defeats the only reason the colours are there.
- With four players the scorecard was cut off; it grows and scrolls inside itself now.

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

