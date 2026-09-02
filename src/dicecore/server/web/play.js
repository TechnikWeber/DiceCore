/*
 * The game screen: lobby → setup → play → result.
 *
 * The screen has exactly one state at a time and one function decides which, so it can
 * never be halfway between two of them. The first version had no lobby at all — it opened
 * straight into whatever mode happened to be configured and started reading the tray, which
 * meant a player was watching numbers change with no idea what was going on. Nothing reads
 * the tray now until a game has actually been started.
 *
 * Everything is reachable by tapping. Names can be typed if somebody wants to, but a table
 * with no keyboard has to be able to play, so every default is already right.
 */

const $ = (id) => document.getElementById(id);
const state = {
  view: "loading", options: null, game: null, last: null,
  wizard: null, socket: null, retry: 1000,
  //: Who this DiceCore is playing with: hosting a table, sitting at one, or neither.
  table: null,
  //: Which dice: the camera's, or the simulator's.
  dice: null,
};

//: This instance is a guest at somebody else's table. Everything changes when it is: there
//: is no game here to touch, only a mirror of theirs, and every move is a request.
const away = () => Boolean(state.table && state.table.guest && state.table.guest.connected);
const hosting = () => Boolean(state.table && state.table.hosting && state.table.hosting.open);
//: Whether this screen may make the current move. Locally everyone shares one screen, so
//: it always may. At a table it may not: a guest waits for its seat, and — the one that is
//: easy to miss — the *host* must not throw for a guest either. The host's tray has nothing
//: to do with the dice in somebody else's room.
const myTurn = () => {
  if (away()) return Boolean(state.table.guest.my_turn);
  if (!hosting()) return true;
  const game = state.game;
  if (!game || !game.running) return true;
  const seat = (state.table.hosting.seats || [])[game.turn.player];
  return !seat || !seat.remote;
};
//: Simulated dice, thrown from the screen. A camera cannot be asked to roll.
const canThrow = () => Boolean(state.dice ? state.dice.simulated
                                          : (state.table && state.table.can_throw));

const escapeHtml = (text) => String(text).replace(/[&<>"]/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const PALETTE = ["#5b8dff", "#3ecf8e", "#e0a94a", "#f0806f", "#c084fc", "#4dd0e1",
                 "#f472b6", "#a3e635"];

async function post(path, body) {
  const response = await fetch(path, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  const data = await response.json().catch(() => ({}));
  if (data.game) { state.game = data.game; }
  else if (data.turn) { state.game = data; }
  if (data.detail) state.flash = data.detail;
  route();
  return data;
}

//: Every move goes through here, and only this function knows where it goes: to this
//: instance's own game, or up the wire to the host of the table it is sitting at. Without
//: it every button would need to know whether it is playing at home or away.
async function act(name, body) {
  if (away()) return post("/api/v1/table/act", { action: name, ...(body || {}) });
  return post(`/api/v1/game/${name}`, body);
}

// --- pips -------------------------------------------------------------------

//: Which of the nine grid cells are inked, per pip count. Drawn rather than written,
//: because from across a table dots read faster than a digit.
const PIPS = {
  1: [4], 2: [0, 8], 3: [0, 4, 8], 4: [0, 2, 6, 8], 5: [0, 2, 4, 6, 8],
  6: [0, 2, 3, 5, 6, 8],
};

function dieFace(die, paint) {
  if (die.kind === "d6" && PIPS[die.value]) {
    const on = new Set(PIPS[die.value]);
    const ink = paint ? `style="background:${paint[1]}"` : "";
    return `<span class="face">${Array.from({ length: 9 }, (_, i) =>
      `<span class="${on.has(i) ? "" : "off"}" ${on.has(i) ? ink : ""}></span>`).join("")}</span>`;
  }
  return escapeHtml(die.value === 0 && die.kind !== "d10" ? "?" : die.value);
}

// --- 1. the lobby -----------------------------------------------------------

const GROUPS = [
  ["Games", ["board", "turns"], "Played round the table, with turns and a score."],
  ["Just show the numbers", ["read"], "No turns, no players — DiceCore reads and reports."],
  ["Tools", ["tool"], "For the workshop rather than the table."],
];

//: One line at the top of the lobby saying who this DiceCore is playing with. It is the
//: only place online play is visible before a game starts, so it is never hidden.
function onlineStrip() {
  const table = state.table || {};
  const seats = ((table.hosting || {}).seats || []).length;
  if (hosting()) {
    return `<div class="strip"><b>Hosting a table</b>
      <span>${seats} seat${seats === 1 ? "" : "s"} · others join at
      <code>${escapeHtml(table.address || "—")}</code></span>
      <button class="quiet" id="btn-table">Manage table</button></div>`;
  }
  if (away()) {
    return `<div class="strip"><b>At ${escapeHtml(state.table.guest.address || "a table")}</b>
      <span>waiting for the host to start a game</span>
      <button class="quiet" id="btn-table">Leave</button></div>`;
  }
  return `<div class="strip quiet-strip"><b>Playing here</b>
    <span>Everyone at this screen. Others can join over the network instead.</span>
    <button class="quiet" id="btn-table">Play online</button></div>`;
}

//: Real dice or simulated ones, as one switch at the top of the lobby.
//:
//: It is a setting, and it lives in Setup as well — but nobody looks in Setup for "I have
//: no dice tower yet, can I still play". The answer to that has to be on the page you
//: arrive at, in words rather than in a list of six capture backends.
function diceStrip() {
  const dice = state.dice || {};
  const simulated = Boolean(dice.simulated);
  const said = simulated
    ? "Drawn and read by DiceCore itself. No camera, no tower — throw from this screen."
    : "Thrown into the tower and read by the camera over the landing area.";
  return `<div class="strip ${dice.problem ? "warn-strip" : "quiet-strip"}">
    <b>${simulated ? "Simulated dice" : "Real dice"}</b>
    <span>${escapeHtml(dice.problem || said)}</span>
    <div class="switch" data-on="${simulated ? "sim" : "real"}">
      <button data-dice="real" class="${simulated ? "" : "on"}">Real</button>
      <button data-dice="sim" class="${simulated ? "on" : ""}">Simulated</button>
    </div>
  </div>`;
}

function renderLobby() {
  const modes = state.options.modes;
  $("app").className = "lobby";
  $("app").innerHTML = `
    ${diceStrip()}
    ${onlineStrip()}
    <h1>What are we playing?</h1>
    <p class="lead">Pick a game. Nothing is read from the tray until one is running.</p>
    ${GROUPS.map(([title, families, blurb]) => {
      const tiles = modes.filter((m) => families.includes(m.family));
      if (!tiles.length) return "";
      return `<section class="group"><h2>${title}</h2>
        <p class="lead" style="margin:-6px 0 12px">${blurb}</p>
        <div class="tiles">${tiles.map((mode) => `
          <button class="tile" data-mode="${mode.id}">
            <b>${escapeHtml(mode.label)}</b>
            <span>${escapeHtml(mode.blurb)}</span>
            <span class="dice-count">${escapeHtml(mode.dice)} dice</span>
          </button>`).join("")}</div></section>`;
    }).join("")}`;

  $("app").querySelectorAll("[data-mode]").forEach((tile) => {
    tile.onclick = () => openWizard(tile.dataset.mode);
  });
  $("btn-table").onclick = () => { state.view = "table"; route(); };
  $("app").querySelectorAll("[data-dice]").forEach((button) => {
    button.onclick = async () => {
      const simulated = button.dataset.dice === "sim";
      if (simulated === Boolean((state.dice || {}).simulated)) return;
      button.closest(".switch").dataset.on = simulated ? "sim" : "real";
      state.dice = await post("/api/v1/dice", { simulated });
      route();
    };
  });
}

// --- 1b. the table: playing against other DiceCores --------------------------

//: Addresses that have worked before, so a table with no keyboard can re-join by tapping.
const KNOWN = "dicecore.tables";
const known = () => { try { return JSON.parse(localStorage.getItem(KNOWN)) || []; }
                      catch (e) { return []; } };
const remember = (address) => {
  try {
    localStorage.setItem(KNOWN,
      JSON.stringify([address, ...known().filter((a) => a !== address)].slice(0, 6)));
  } catch (e) { /* a browser that refuses storage still plays; it just forgets. */ }
};

function seatList(seats, mySeat) {
  if (!seats || !seats.length) return `<p class="lead">Nobody has sat down yet.</p>`;
  return `<div class="seats">${seats.map((seat, index) => `
    <div class="seat ${seat.connected ? "" : "gone"} ${index === mySeat ? "me" : ""}">
      <span class="dot" style="background:${PALETTE[index % PALETTE.length]}"></span>
      <b>${escapeHtml(seat.name)}</b>
      <span>${seat.remote ? (seat.connected ? "connected" : "lost the connection")
                          : "at this screen"}</span>
    </div>`).join("")}</div>`;
}

function renderTable() {
  const table = state.table || {};
  const host = table.hosting || {};
  const visitor = table.guest || {};
  $("app").className = "wizard";

  if (host.open) {
    const others = (table.addresses || []).slice(1);
    $("app").innerHTML = `
      <h1>Your table is open</h1>
      <p class="lead">Others open their own DiceCore, tap <b>Play online</b> → <b>Join</b>
         and type this address. Same network, or the same Tailscale/Hamachi network.</p>
      <div class="address">${escapeHtml(table.address || "not reachable from anywhere")}</div>
      ${others.length ? `<p class="lead" style="margin:-12px 0 22px">Also reachable as
        ${others.map((a) => `<code>${escapeHtml(a)}</code>`).join(" · ")}</p>` : ""}
      <section class="step"><h2>Seats (${host.seats.length} of ${host.max_seats})</h2>
        ${seatList(host.seats, 0)}</section>
      <p class="lead">The seats are the players. Pick a game and start it — everyone at the
         table gets the same board, and each of them throws on their own DiceCore.</p>
      <div class="start-row">
        <button class="primary big" id="btn-pick">Pick a game</button>
        <button class="quiet" id="btn-close">Close the table</button>
      </div>`;
    $("btn-pick").onclick = () => { state.view = "lobby"; route(); };
    $("btn-close").onclick = async () => {
      await post("/api/v1/table/close");
      await refreshTable();
      state.view = "lobby";
      route();
    };
    return;
  }

  if (visitor.active) {
    $("app").innerHTML = `
      <h1>${visitor.connected ? "You are at the table" : "Connecting…"}</h1>
      <p class="lead">${escapeHtml(visitor.address || "")} —
        ${visitor.connected
          ? `you are seat ${visitor.seat + 1}. The host starts the game.`
          : "trying again; leave the page open."}</p>
      ${visitor.problem ? `<div class="note warn">${escapeHtml(visitor.problem)}</div>` : ""}
      <section class="step"><h2>Seats</h2>${seatList(visitor.seats, visitor.seat)}</section>
      <div class="start-row">
        <button class="quiet" id="btn-leave-table">Leave the table</button>
      </div>`;
    $("btn-leave-table").onclick = async () => {
      await post("/api/v1/table/leave");
      await refreshTable();
      state.view = "lobby";
      route();
    };
    return;
  }

  const name = (state.game && state.game.players && state.game.players[0]) || "Player 1";
  $("app").innerHTML = `
    <h1>Play online</h1>
    <p class="lead">Two or more DiceCores on the same network play one game, turn by turn.
       Everyone sees every roll as it lands. One of you hosts; the rest join.</p>

    <section class="step">
      <h2>Host it here</h2>
      <p class="lead" style="margin:-6px 0 12px">This DiceCore owns the game. Your scorecard
         is the real one, and it survives a guest losing their connection.</p>
      <div class="start-row"><button class="primary big" id="btn-open">Open a table</button></div>
    </section>

    <section class="step">
      <h2>Or join somebody else's</h2>
      <div class="join">
        <input id="join-address" placeholder="dicecore.local:8099 or 100.x.y.z:8099"
               spellcheck="false" autocapitalize="off">
        <input id="join-name" value="${escapeHtml(name)}" maxlength="24" spellcheck="false">
        <button class="primary" id="btn-join">Join</button>
      </div>
      ${known().length ? `<div class="choices" style="margin-top:12px">${known().map((a) =>
        `<button class="choice" data-known="${escapeHtml(a)}">${escapeHtml(a)}</button>`)
        .join("")}</div>` : ""}
      <p class="lead" style="margin-top:14px">You keep your own dice — camera or
         simulator — and throw on this DiceCore when it is your turn.</p>
    </section>

    <div class="start-row"><button class="quiet" id="btn-back">Back</button></div>`;

  $("btn-open").onclick = async () => {
    await post("/api/v1/table/host", { name });
    await refreshTable();
    route();
  };
  const doJoin = async () => {
    const address = $("join-address").value.trim();
    if (!address) return;
    $("btn-join").disabled = true;
    const answer = await post("/api/v1/table/join",
      { address, name: $("join-name").value.trim() || name });
    $("btn-join").disabled = false;
    if (answer.ok) remember(address);
    await refreshTable();
    route();
  };
  $("btn-join").onclick = doJoin;
  $("join-address").onkeydown = (event) => { if (event.key === "Enter") doJoin(); };
  $("app").querySelectorAll("[data-known]").forEach((button) => {
    button.onclick = () => { $("join-address").value = button.dataset.known; doJoin(); };
  });
  $("btn-back").onclick = () => { state.view = "lobby"; route(); };
}

async function refreshTable() {
  state.table = await (await fetch("/api/v1/table")).json().catch(() => state.table);
}

// --- 2. the setup wizard ----------------------------------------------------

//: Only the settings a table actually decides, offered as buttons. Everything else keeps
//: its default, and everything here is optional — Start works on the first tap.
const OPTIONS = {
  yahtzee: [["chips", "Chips per player, for the whole game", [0, 1, 2, 3, 4]]],
  yahtzee_extreme: [["chips", "Chips per player, for the whole game", [0, 1, 2, 3, 4]]],
  farkle: [["target", "Play to", [3000, 5000, 10000, 20000]],
           ["entry", "Needed to get on the board", [0, 350, 500, 1000]]],
  pool: [["threshold", "A die counts from", [3, 4, 5, 6]]],
  best: [["take", "Which die counts", ["high", "low"]]],
  under: [["target", "Target", [30, 50, 70, 90]]],
};

//: The next colour nobody else is using. Cycling blindly through the palette handed two
//: players the same colour, which defeats the only reason the colours are there.
function freeColour(players, after = -1, skip = -1) {
  const taken = new Set(players.filter((_, i) => i !== skip).map((p) => p.colour));
  for (let step = 1; step <= PALETTE.length; step += 1) {
    const colour = PALETTE[(after + step + PALETTE.length) % PALETTE.length];
    if (!taken.has(colour)) return colour;
  }
  return PALETTE[(after + 1) % PALETTE.length];
}

function openWizard(modeId) {
  const mode = state.options.modes.find((m) => m.id === modeId);
  const previous = state.game && state.game.mode === modeId ? state.game : null;
  // At an open table the players are whoever sat down. Offering a player count there would
  // be a control that quietly disagrees with the seat list.
  const seats = hosting() ? state.table.hosting.seats : null;
  const count = seats ? seats.length : (previous ? previous.players.length : 2);
  const players = [];
  for (let i = 0; i < count; i += 1) {
    players.push({
      name: (seats && seats[i].name) || (previous && previous.players[i]) || `Player ${i + 1}`,
      colour: (previous && previous.colours[i]) || freeColour(players, i - 1),
      fixed: Boolean(seats),
    });
  }
  state.wizard = { mode, players, params: { ...mode.defaults }, seated: Boolean(seats) };
  state.view = "wizard";
  route();
}

function needsPlayers(mode) {
  return mode.family === "board" || mode.family === "turns";
}

function renderWizard() {
  const wizard = state.wizard;
  const mode = wizard.mode;
  $("app").className = "wizard";
  const options = OPTIONS[mode.id] || [];

  $("app").innerHTML = `
    <h1>${escapeHtml(mode.label)}</h1>
    <p class="lead">${escapeHtml(mode.blurb)} Uses ${escapeHtml(mode.dice)} dice.</p>

    ${needsPlayers(mode) ? `
      ${wizard.seated ? "" : `
      <section class="step">
        <h2>How many are playing?</h2>
        <div class="choices">${[1, 2, 3, 4, 5, 6].map((n) =>
          `<button class="choice ${n === wizard.players.length ? "on" : ""}"
             data-count="${n}">${n}</button>`).join("")}</div>
      </section>`}
      <section class="step">
        <h2>${wizard.seated ? "Who is at the table" : "Who"}</h2>
        <div class="roster">${wizard.players.map((player, index) => `
          <div class="player">
            <button class="swatch" data-swatch="${index}"
                    style="background:${player.colour}" title="Tap for another colour"></button>
            <input data-name="${index}" value="${escapeHtml(player.name)}"
                   maxlength="24" spellcheck="false" ${player.fixed ? "disabled" : ""}>
            <span class="hint">${player.fixed ? "from the table" : "tap to rename"}</span>
          </div>`).join("")}</div>
      </section>` : ""}

    ${options.map(([key, label, values]) => `
      <section class="step">
        <h2>${escapeHtml(label)}</h2>
        <div class="choices">${values.map((value) =>
          `<button class="choice ${String(wizard.params[key]) === String(value) ? "on" : ""}"
             data-opt="${key}" data-value="${escapeHtml(value)}">${escapeHtml(value)}</button>`)
          .join("")}</div>
      </section>`).join("")}

    <div class="start-row">
      <button class="primary big" id="btn-start">Start ${escapeHtml(mode.label)}</button>
      <button class="quiet" id="btn-back">Pick another game</button>
    </div>`;

  $("app").querySelectorAll("[data-count]").forEach((button) => {
    button.onclick = () => {
      const count = Number(button.dataset.count);
      const players = wizard.players.slice(0, count);
      while (players.length < count) {
        players.push({ name: `Player ${players.length + 1}`, colour: freeColour(players) });
      }
      wizard.players = players;
      route();
    };
  });
  $("app").querySelectorAll("[data-swatch]").forEach((button) => {
    button.onclick = () => {
      const index = Number(button.dataset.swatch);
      const at = PALETTE.indexOf(wizard.players[index].colour);
      wizard.players[index].colour = freeColour(wizard.players, at, index);
      route();
    };
  });
  $("app").querySelectorAll("[data-name]").forEach((input) => {
    input.oninput = () => {
      wizard.players[Number(input.dataset.name)].name = input.value;
    };
  });
  $("app").querySelectorAll("[data-opt]").forEach((button) => {
    button.onclick = () => {
      const raw = button.dataset.value;
      wizard.params[button.dataset.opt] = /^-?\d+$/.test(raw) ? Number(raw) : raw;
      route();
    };
  });
  $("btn-back").onclick = () => { state.view = "lobby"; route(); };
  $("btn-start").onclick = async () => {
    const players = needsPlayers(mode) ? wizard.players : [{ name: "Player 1" }];
    await post("/api/v1/game/start", {
      mode: mode.id,
      players: players.map((p, i) => p.name.trim() || `Player ${i + 1}`),
      colours: players.map((p) => p.colour),
      params: wizard.params,
    });
    state.view = "playing";
    connect();
    route();
  };
}

// --- 3. the game ------------------------------------------------------------

function renderGame() {
  const game = state.game;
  const roll = state.last;
  const reading = (game.rules.multi ? game.reading : (roll && roll.reading)) || {};
  const headline = reading.headline
    || (!game.rules.multi && roll && roll.count ? String(roll.total) : null);
  const colour = game.colours[game.turn.player] || PALETTE[0];
  const waiting = game.turn.rolls_used === 0;

  $("app").className = "";
  $("app").innerHTML = `
    <section class="board">
      <div class="turnbar" id="turnbar"></div>
      <div class="headline" id="headline"></div>
      <div class="detail" id="detail"></div>
      <div class="dice" id="dice"></div>
      <div id="notes"></div>
      <div class="actions">
        <button class="primary big" id="btn-throw" hidden>Throw</button>
        <button class="primary" id="btn-aside" hidden>Set aside</button>
        <button id="btn-bank" hidden>Bank</button>
        <button class="chip" id="btn-chip" hidden>Spend a chip</button>
        <button id="btn-undo" hidden>Undo that</button>
        <button id="btn-next" hidden>End turn</button>
      </div>
    </section>
    <aside id="side" hidden>
      <div class="card" id="card"></div>
      <div class="card" style="margin-top:16px"><h2>Last turns</h2>
        <div class="log" id="log"></div></div>
    </aside>`;

  $("headline").textContent = headline || "";
  $("headline").className = "headline"
    + ((headline || "").length > 7 ? " small" : "")
    + (reading.celebrate ? " celebrate" : "")
    + (reading.lament ? " lament" : "");
  // Once per roll, not once per render: the screen redraws on every hold, every chip and
  // every message, and confetti on all of those would be a strobe light.
  const stamp = `${game.turn.number}:${game.turn.rolls_used}:${headline}`;
  if (reading.celebrate && stamp !== state.cheered) {
    state.cheered = stamp;
    cheer();
  } else if (!reading.celebrate) {
    state.cheered = state.cheered === stamp ? state.cheered : null;
  }
  $("detail").textContent = reading.detail || (!game.rules.multi && roll ? roll.notation : "");
  if (waiting && !headline) {
    // A visible "your throw" beats a blank screen: the tray is being watched and the
    // player should be able to see that without being told. Online it names whoever it is
    // waiting for, because on your screen "Throw the dice" would be an instruction to you.
    const label = myTurn() ? "Throw the dice"
      : `${escapeHtml(game.current_player)} is throwing`;
    $("headline").innerHTML =
      `<span class="waiting"><i style="background:${colour}"></i>${label}</span>`;
  }

  renderTurn(game);
  renderDice(game);
  renderBoard(game);
  renderLog(game);
  renderActions(game, roll);
}

function renderTurn(game) {
  const turn = game.turn;
  const colour = game.colours[turn.player] || PALETTE[0];
  const chunks = [`<span class="dot" style="background:${colour}"></span>`,
                  `<span><b>${escapeHtml(game.current_player)}</b></span>`];
  if (away()) {
    chunks.push(myTurn()
      ? `<span class="seat-badge on">your turn</span>`
      : `<span class="seat-badge">watching</span>`);
  }
  if (turn.unlimited) {
    const farkle = game.farkle || {};
    chunks.push(`<span>· turn ${turn.number} · ${farkle.turn_points || 0} at stake`
      + ` · ${farkle.dice_left || 6} dice</span>`);
  } else if (game.rules.multi) {
    const base = game.rules.rolls;
    const dots = [];
    for (let i = 0; i < turn.rolls_allowed; i += 1) {
      dots.push(`<i class="${i >= base ? "chip" : ""} ${i < turn.rolls_used ? "used" : ""}"></i>`);
    }
    for (let i = 0; i < turn.chips_left; i += 1) dots.push(`<i class="chip"></i>`);
    chunks.push(`<span class="pips-left">${dots.join("")}</span>`,
      `<span>throw ${turn.rolls_used} of ${turn.rolls_allowed}`
      + (turn.chips_left ? ` · ${turn.chips_left} chip${turn.chips_left > 1 ? "s" : ""}` : "")
      + ` · turn ${turn.number}</span>`);
  } else {
    chunks.push(`<span>turn ${turn.number}</span>`);
  }
  $("turnbar").innerHTML = chunks.join(" ");
}

//: Swatches for the colours the engine can name, so a screen can show the dice as they
//: actually are rather than as five identical white squares.
const DIE_COLOURS = {
  white: ["#eef1f5", "#14181f"], black: ["#23262c", "#eef1f5"],
  grey: ["#8b93a1", "#14181f"], red: ["#e5484d", "#fff"], orange: ["#f0862a", "#14181f"],
  yellow: ["#f5d020", "#14181f"], green: ["#3ecf8e", "#14181f"],
  cyan: ["#3fc5d8", "#14181f"], blue: ["#4f7ff5", "#fff"], purple: ["#a56ef0", "#fff"],
  pink: ["#f472b6", "#14181f"],
};

function renderDice(game) {
  $("dice").innerHTML = game.turn.dice.map((die, index) => {
    const paint = DIE_COLOURS[die.colour];
    const style = paint ? `background:${paint[0]};color:${paint[1]}` : "";
    return `<div class="die ${die.held ? "held" : ""}" data-index="${index}"
      style="${style}" title="${escapeHtml(die.kind)}${
        die.colour ? `, ${escapeHtml(die.colour)}` : ""}">${dieFace(die, paint)}</div>`;
  }).join("");
  if (game.rules.holds && myTurn()) {
    $("dice").querySelectorAll(".die").forEach((node) => {
      node.onclick = () => act("hold", { index: Number(node.dataset.index) });
    });
  } else {
    $("dice").querySelectorAll(".die").forEach((n) => (n.style.cursor = "default"));
  }
}

function renderActions(game, roll) {
  const show = (id, visible) => ($(id).hidden = !visible);
  const mine = myTurn();
  // Somebody else is throwing. Their move is not yours to make, and a live button that
  // would only come back refused is worse than no button.
  const turn = game.turn;
  const spent = turn.unlimited ? false : turn.rolls_used >= turn.rolls_allowed;
  show("btn-throw", canThrow() && mine && !spent && !(game.farkle && game.farkle.farkled));
  $("btn-throw").textContent = turn.rolls_used === 0 || turn.unlimited
    ? "Throw the dice" : `Throw again (${turn.rolls_used} of ${turn.rolls_allowed})`;
  $("btn-throw").onclick = async () => {
    $("btn-throw").disabled = true;
    try {
      // The dice come back from the throw itself rather than being waited for on the
      // stream: the button was pressed here, and a delay between pressing it and seeing
      // the dice is the one thing a simulator has no excuse for.
      const thrown = await post("/api/v1/throw");
      if (thrown && thrown.dice) { state.last = thrown; route(); }
    } finally { $("btn-throw").disabled = false; }
  };

  show("btn-chip", Boolean(game.rules.chips) && mine);
  $("btn-chip").disabled = !game.turn.can_spend_chip;
  show("btn-aside", Boolean(game.farkle) && mine);
  show("btn-bank", Boolean(game.farkle) && mine);
  if (game.farkle) {
    $("btn-aside").disabled = !(game.selection && game.selection.points) || game.farkle.farkled;
    $("btn-bank").disabled = game.turn.rolls_used === 0;
    $("btn-bank").textContent = game.farkle.farkled
      ? "Take the loss" : `Bank ${game.farkle.turn_points}`;
  }
  show("btn-next", !game.farkle && !game.cards.length && mine);
  $("btn-next").disabled = game.turn.rolls_used === 0;
  // Undo reaches back into a finished turn, so only the host may use it: a guest undoing
  // somebody else's booking from across the network is not a game, it is an argument.
  show("btn-undo", Boolean(game.can_undo) && !away());
  $("btn-undo").onclick = () => post("/api/v1/game/undo");

  $("btn-chip").onclick = () => act("chip");
  $("btn-aside").onclick = () => act("aside");
  $("btn-bank").onclick = () => act("bank");
  $("btn-next").onclick = () => act("next");

  const message = state.flash || game.message
    || (away() && state.table.guest.problem)
    || (roll && roll.verdict === "void"
        ? "That roll was voided — the dice changed after they were read." : "");
  $("notes").innerHTML = message
    ? `<div class="note ${/farkle|void/i.test(message) ? "bad" : "warn"}">${escapeHtml(message)}</div>`
    : "";
  state.flash = "";
}

// --- the boards -------------------------------------------------------------

function renderCard(game) {
  if (!game.cards.length || !game.sheet) return false;
  const sheet = game.sheet;
  const label = (c) => sheet.labels[c] || c;
  const mine = game.turn.player;
  const rows = [];

  const section = (title, categories) => {
    rows.push(`<tr class="section"><td colspan="${game.cards.length + 1}">${title}</td></tr>`);
    for (const category of categories) {
      const cells = game.cards.map((card, index) => {
        const booked = card.scores[category];
        const active = index === mine;
        if (booked !== null && booked !== undefined) {
          return `<td class="${active ? "you" : ""}">${booked}</td>`;
        }
        if (!active) return `<td></td>`;
        const worth = game.options[category];
        // What each open box is worth is shown to everyone, whoever's turn it is: watching
        // somebody decide is most of the game, and a row of dots says nothing.
        const rolled = game.turn.rolls_used > 0;
        const playable = rolled && myTurn();
        return `<td class="you open"><button data-book="${category}"
          class="${worth ? "worth" : ""}" ${playable ? "" : "disabled"}
          title="Book ${escapeHtml(label(category))}">${rolled ? (worth || "—") : "·"}</button></td>`;
      }).join("");
      rows.push(`<tr><td>${escapeHtml(label(category))}</td>${cells}</tr>`);
    }
  };

  section("Upper", sheet.upper);
  rows.push(`<tr><td>Bonus at ${sheet.bonus_at}</td>${game.cards.map((c) =>
    `<td>${c.bonus ? `+${c.bonus}` : (c.to_bonus ? `${c.to_bonus} to go` : "0")}</td>`)
    .join("")}</tr>`);
  section("Lower", sheet.lower);
  rows.push(`<tr class="total"><td>Total</td>${game.cards.map((c, i) =>
    `<td class="${i === game.leader ? "leader" : ""}">${c.total}</td>`).join("")}</tr>`);

  $("card").innerHTML = `<h2>${escapeHtml(sheet.label)}</h2><table>
    <tr><th></th>${game.cards.map((c, i) =>
      `<th class="${i === mine ? "you" : ""}"><span class="dot"
         style="background:${game.colours[i]}"></span>${escapeHtml(c.name)}</th>`).join("")}</tr>
    ${rows.join("")}</table>`;

  $("card").querySelectorAll("[data-book]").forEach((button) => {
    button.onclick = () => {
      const worth = game.options[button.dataset.book] || 0;
      // Booking a zero is a real move — crossing a box out — but it should be deliberate.
      if (!worth && !confirm(`Cross out ${label(button.dataset.book)} for 0?`)) return;
      act("book", { category: button.dataset.book, cross_out: !worth });
    };
  });
  return true;
}

function renderFarkle(game) {
  const farkle = game.farkle;
  if (!farkle) return false;
  const selection = game.selection || { points: 0 };
  const rows = game.players.map((name, index) => `
    <tr>
      <td class="${index === game.turn.player ? "you" : ""}"><span class="dot"
        style="background:${game.colours[index]}"></span>${escapeHtml(name)}</td>
      <td>${farkle.banked[index]}</td>
      <td>${farkle.on_board[index] ? "" : `needs ${farkle.entry}`}</td>
    </tr>`).join("");

  $("card").innerHTML = `<h2>Farkle — first to ${farkle.target}</h2>
    <table><tr><th></th><th>Banked</th><th></th></tr>${rows}
      <tr class="total"><td>This turn</td><td>${farkle.turn_points}</td>
        <td>${farkle.dice_left} dice</td></tr></table>
    ${farkle.farkled
      ? `<p class="log" style="color:var(--bad)">Farkle — the turn is lost.</p>`
      : `<p class="log">Set aside every die that scores, then bank or throw again.
         ${selection.points ? `Selected: <b>${selection.points}</b>` : "Nothing selected."}</p>`}`;
  return true;
}

function renderBoard(game) {
  const has = renderCard(game) || renderFarkle(game);
  $("side").hidden = !has;
  $("app").classList.toggle("with-card", has);
  return has;
}

function renderLog(game) {
  $("log").innerHTML = game.log.length
    ? game.log.map((entry) => `<div><span class="dot"
        style="background:${game.colours[entry.player] || "#888"}"></span>
        ${entry.values.join(", ")}${entry.booked
          ? ` → ${escapeHtml((game.sheet && game.sheet.labels[entry.booked]) || entry.booked)}
             ${entry.points}`
          : (entry.headline ? ` → ${escapeHtml(entry.headline)}` : "")}</div>`).join("")
    : `<div>Nothing yet.</div>`;
}

// --- 4. the result ----------------------------------------------------------

function renderResultScreen() {
  const game = state.game;
  const scores = game.farkle
    ? game.farkle.banked
    : game.cards.map((card) => card.total);
  const order = scores.map((score, index) => ({ score, index }))
    .sort((a, b) => b.score - a.score);
  const best = order.length ? order[0].score : 0;

  $("app").className = "wizard";
  $("app").innerHTML = `
    <h1>${escapeHtml(game.players[game.leader] || "Nobody")} wins</h1>
    <p class="lead">${escapeHtml(state.options.modes.find((m) => m.id === game.mode).label)},
       ${game.turn.number - 1} turns.</p>
    <div class="standings">${order.map((row, rank) => `
      <div class="standing ${row.score === best ? "win" : ""}">
        <span class="rank">${rank + 1}.</span>
        <span class="dot" style="background:${game.colours[row.index]}"></span>
        <span class="name">${escapeHtml(game.players[row.index])}</span>
        <span class="score">${row.score}</span>
      </div>`).join("")}</div>
    <div class="start-row">
      <button class="primary big" id="btn-again">Play again</button>
      <button class="quiet" id="btn-lobby">Pick another game</button>
    </div>`;

  $("btn-again").onclick = async () => {
    await post("/api/v1/game/start", {
      mode: game.mode, players: game.players, colours: game.colours,
    });
    state.view = "playing";
    route();
  };
  $("btn-lobby").onclick = () => leaveGame();
}

// --- routing ----------------------------------------------------------------

async function leaveGame() {
  await post("/api/v1/game/stop");
  state.view = "lobby";
  route();
}

//: One line in the header saying what this DiceCore is doing right now. Written after the
//: screen is decided rather than when a message arrives, so it cannot contradict it.
function linkState() {
  const data = state.link;
  if (!data) return "…";
  if (data.error) return data.error;
  const game = state.game;
  const playing = game && game.running;
  if (playing && !myTurn()) return `waiting for ${game.current_player}`;
  if (data.idle) return away() ? "at the table" : "idle";
  return data.manual ? "your throw" : "watching the tray";
}

function route() {
  // A guest has no game of its own: what it draws is the host's, mirrored. Deciding that
  // here rather than in each renderer is what keeps "at home" and "away" from being two
  // screens that drift apart.
  if (away()) {
    const mirror = state.table.guest.game;
    if (mirror) state.game = mirror;
    $("btn-quit").hidden = false;
    $("btn-quit").textContent = "Leave the table";
    $("who").textContent = "";
    $("game-name").textContent = mirror && mirror.running
      ? `${mirror.mode.replace(/_/g, " ")} · away` : "at a table";
    $("link-state").textContent = linkState();
    if (mirror && mirror.running) return renderGame();
    return renderTable();
  }
  $("btn-quit").textContent = "Leave game";

  const game = state.game;
  if (state.view === "playing" && game && game.complete) state.view = "over";
  if (state.view === "playing" && game && !game.running) state.view = "lobby";

  $("btn-quit").hidden = state.view !== "playing" && state.view !== "over";
  $("game-name").textContent = state.view === "playing" && game
    ? game.mode.replace(/_/g, " ") + (hosting() ? " · hosting" : "") : "";
  $("who").textContent = { lobby: "DiceCore", wizard: "New game", table: "Play online",
                           playing: "", over: "Result" }[state.view] ?? "DiceCore";

  $("link-state").textContent = linkState();
  if (state.view === "lobby") return renderLobby();
  if (state.view === "table") return renderTable();
  if (state.view === "wizard") return renderWizard();
  if (state.view === "over") return renderResultScreen();
  if (state.view === "playing" && game) return renderGame();
  $("app").innerHTML = `<p class="lead">Loading…</p>`;
}

// --- the celebration --------------------------------------------------------

const CONFETTI = ["#5b8dff", "#3ecf8e", "#e0a94a", "#f0806f", "#c084fc", "#4dd0e1"];

function cheer() {
  const ring = document.createElement("div");
  ring.className = "ring";
  document.body.appendChild(ring);
  setTimeout(() => ring.remove(), 1100);

  const burst = document.createElement("div");
  burst.className = "burst";
  // Thirty pieces: enough to read as a celebration from the far end of a table, few enough
  // that a Pi driving a television does not stutter over it.
  burst.innerHTML = Array.from({ length: 30 }, () => {
    const angle = Math.random() * Math.PI * 2;
    const far = 180 + Math.random() * 340;
    return `<i style="--dx:${Math.cos(angle) * far}px; --dy:${Math.sin(angle) * far}px;
      background:${CONFETTI[Math.floor(Math.random() * CONFETTI.length)]};
      animation-delay:${Math.random() * 0.18}s"></i>`;
  }).join("");
  document.body.appendChild(burst);
  setTimeout(() => burst.remove(), 1900);
}

// --- the connection ---------------------------------------------------------

function connect() {
  if (state.socket && state.socket.readyState <= 1) return;
  const socket = new WebSocket(`${location.origin.replace(/^http/, "ws")}/api/v1/events`);
  state.socket = socket;
  socket.onopen = () => { state.retry = 1000; };
  socket.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.error) { state.link = data; $("link-state").textContent = data.error; return; }
    if (data.table) state.table = data.table;
    if (data.dice) state.dice = data.dice;
    if (data.game) state.game = data.game;
    if (!data.idle && !data.away) state.last = data;
    state.link = data;
    route();
  };
  socket.onclose = () => {
    $("link-state").textContent = "reconnecting…";
    // Backing off matters: this page is left open all evening, and a Pi that is restarting
    // should not be hammered by a television.
    setTimeout(connect, state.retry);
    state.retry = Math.min(state.retry * 2, 15000);
  };
}

//: The stream is only offered when it has been switched on: it is a camera, and leaving
//: one running on an unauthenticated port is the room's decision, not a default.
async function setupCamera() {
  const health = await (await fetch("/api/v1/health")).json().catch(() => ({}));
  if (!health.stream) return;
  $("btn-camera").hidden = false;
  $("btn-camera").onclick = () => {
    const panel = $("livecam");
    panel.hidden = !panel.hidden;
    // The <img> is only given a source while it is visible: an MJPEG connection left open
    // behind a hidden element keeps the camera busy for nobody.
    $("livecam-img").src = panel.hidden ? "" : `/api/v1/stream.mjpg?t=${Date.now()}`;
    $("btn-camera").textContent = panel.hidden ? "Camera" : "Hide camera";
  };
}

$("btn-quit").onclick = async () => {
  if (away()) {
    if (!confirm("Leave this table? The game carries on without you.")) return;
    await post("/api/v1/table/leave");
    await refreshTable();
    state.view = "lobby";
    return route();
  }
  if (confirm("Leave this game? The scores are lost.")) leaveGame();
};

(async function boot() {
  state.options = await (await fetch("/api/v1/modes")).json();
  state.dice = await (await fetch("/api/v1/dice")).json().catch(() => null);
  await refreshTable();
  const info = await (await fetch("/api/v1/game")).json();
  state.game = info.game;
  state.last = info.last;
  // Coming back to a game that is still running should land you back in it, not in a lobby
  // that throws it away.
  state.view = info.game.running ? "playing" : "lobby";
  if (away()) state.view = "table";
  route();
  connect();
  setupCamera();
})();
