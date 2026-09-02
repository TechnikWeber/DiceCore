/*
 * The play screen.
 *
 * Reads the websocket, which is also what makes DiceCore keep looking at the tray — opening
 * this page is what starts a game listening. Everything the player can do is a POST to
 * /api/v1/game/*, which is the same door the GPIO buttons knock on, so a table can use
 * either or both without the two disagreeing.
 */

const $ = (id) => document.getElementById(id);
const state = { game: null, last: null, socket: null, retry: 1000 };

const escapeHtml = (text) => String(text).replace(/[&<>"]/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

async function post(path, body) {
  const response = await fetch(path, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  const data = await response.json().catch(() => ({}));
  if (data.game) render(data.game, state.last);
  if (data.detail) note(data.detail, "warn");
  return data;
}

function note(text, kind = "warn") {
  $("notes").innerHTML = `<div class="note ${kind}">${escapeHtml(text)}</div>`;
  clearTimeout(state.noteTimer);
  state.noteTimer = setTimeout(() => ($("notes").innerHTML = ""), 6000);
}

// --- dice -------------------------------------------------------------------

//: Which of the nine grid cells are inked, per pip count. Drawn rather than written,
//: because from across a table dots read faster than a digit.
const PIPS = {
  1: [4], 2: [0, 8], 3: [0, 4, 8], 4: [0, 2, 6, 8], 5: [0, 2, 4, 6, 8],
  6: [0, 2, 3, 5, 6, 8],
};

function dieFace(die) {
  if (die.kind === "d6" && PIPS[die.value]) {
    const on = new Set(PIPS[die.value]);
    return `<span class="face">${Array.from({ length: 9 }, (_, i) =>
      `<span class="${on.has(i) ? "" : "off"}"></span>`).join("")}</span>`;
  }
  return escapeHtml(die.value === 0 && die.kind !== "d10" ? "?" : die.value);
}

function renderDice(game) {
  const dice = game.turn.dice;
  $("dice").innerHTML = dice.map((die, index) => `
    <div class="die ${die.held ? "held" : ""}" data-index="${index}"
         title="${escapeHtml(die.kind)}">${dieFace(die)}</div>`).join("");
  if (game.rules.holds) {
    $("dice").querySelectorAll(".die").forEach((node) => {
      node.onclick = () => post("/api/v1/game/hold", { index: Number(node.dataset.index) });
    });
  } else {
    $("dice").querySelectorAll(".die").forEach((n) => (n.style.cursor = "default"));
  }
}

// --- turn state -------------------------------------------------------------

function renderTurn(game) {
  const turn = game.turn;
  if (!game.rules.multi) { $("turnbar").innerHTML = ""; return; }
  const base = game.rules.rolls;
  const dots = [];
  for (let i = 0; i < turn.rolls_allowed; i += 1) {
    const chip = i >= base;
    dots.push(`<i class="${chip ? "chip" : ""} ${i < turn.rolls_used ? "used" : ""}"></i>`);
  }
  for (let i = 0; i < turn.chips_left; i += 1) dots.push(`<i class="chip"></i>`);
  $("turnbar").innerHTML =
    `<span class="pips-left">${dots.join("")}</span>`
    + `<span>throw ${turn.rolls_used} of ${turn.rolls_allowed}</span>`
    + (turn.chips_left ? `<span>· ${turn.chips_left} chip${turn.chips_left > 1 ? "s" : ""} left</span>` : "")
    + `<span>· turn ${turn.number}</span>`;
}

// --- the scorecard ----------------------------------------------------------

const SECTIONS = [
  ["Upper", ["ones", "twos", "threes", "fours", "fives", "sixes"]],
  ["Lower", ["three_of_a_kind", "four_of_a_kind", "full_house", "small_straight",
             "large_straight", "kniffel", "chance"]],
];
const LABELS = {
  ones: "Ones", twos: "Twos", threes: "Threes", fours: "Fours", fives: "Fives",
  sixes: "Sixes", three_of_a_kind: "Three of a kind", four_of_a_kind: "Four of a kind",
  full_house: "Full house", small_straight: "Small straight",
  large_straight: "Large straight", kniffel: "Kniffel", chance: "Chance",
};

function renderCard(game) {
  if (!game.cards.length) { $("side").hidden = true; $("main").classList.remove("with-card"); return; }
  $("side").hidden = false;
  $("main").classList.add("with-card");

  const mine = game.turn.player;
  const rows = [];
  for (const [title, categories] of SECTIONS) {
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
        const playable = game.turn.rolls_used > 0;
        return `<td class="you open"><button data-book="${category}"
          class="${worth ? "worth" : ""}" ${playable ? "" : "disabled"}
          title="Book ${LABELS[category]}">${playable ? (worth || "—") : "·"}</button></td>`;
      }).join("");
      rows.push(`<tr><td>${LABELS[category]}</td>${cells}</tr>`);
    }
    if (title === "Upper") {
      rows.push(`<tr><td>Bonus at 63</td>${game.cards.map((c) =>
        `<td>${c.bonus ? `+${c.bonus}` : (c.to_bonus ? `${c.to_bonus} to go` : "0")}</td>`)
        .join("")}</tr>`);
    }
  }
  rows.push(`<tr class="total"><td>Total</td>${game.cards.map((c, i) =>
    `<td class="${i === game.leader ? "leader" : ""}">${c.total}</td>`).join("")}</tr>`);

  $("card").innerHTML = `<h2>Scorecard</h2><table>
    <tr><th></th>${game.cards.map((c, i) =>
      `<th class="${i === mine ? "you" : ""}">${escapeHtml(c.name)}</th>`).join("")}</tr>
    ${rows.join("")}</table>
    ${game.complete ? `<p class="leader">Game over — ${escapeHtml(
      game.leader === null ? "it is a tie" : game.cards[game.leader].name + " wins")}.</p>` : ""}`;

  $("card").querySelectorAll("[data-book]").forEach((button) => {
    button.onclick = () => {
      const worth = game.options[button.dataset.book] || 0;
      // Booking a zero is a real move — crossing a box out — but it should be deliberate.
      if (!worth && !confirm(`Cross out ${LABELS[button.dataset.book]} for 0?`)) return;
      post("/api/v1/game/book", { category: button.dataset.book, cross_out: !worth });
    };
  });
}

function renderLog(game) {
  $("log").innerHTML = game.log.length
    ? game.log.map((entry) => `<div>${escapeHtml(game.players[entry.player] || "?")}:
        ${entry.values.join(", ")}${entry.booked
          ? ` → ${LABELS[entry.booked] || entry.booked} ${entry.points}` : ""}</div>`).join("")
    : `<div>Nothing yet.</div>`;
}

// --- the whole screen -------------------------------------------------------

function render(game, roll) {
  state.game = game;
  // In a game with turns the headline belongs to *this turn's* throw, not to whatever the
  // camera looked at a moment ago: once the throws are used up the tray is still being
  // watched, and the newest reading is about dice this turn never rolled.
  const reading = (game.rules.multi ? game.reading : (roll && roll.reading)) || {};
  const headline = reading.headline
    || (!game.rules.multi && roll && roll.count ? String(roll.total) : null);

  $("who").textContent = game.players.length > 1
    ? `${game.current_player}'s turn` : (headline ? "" : "Your throw");
  $("game-name").textContent = game.mode.replace(/_/g, " ");
  $("headline").textContent = headline || "Throw the dice";
  $("headline").className = "headline" + ((headline || "").length > 7 ? " small" : "");
  $("detail").textContent = reading.detail
    || (!game.rules.multi && roll ? roll.notation : "");

  renderTurn(game);
  renderDice(game);
  renderCard(game);
  renderLog(game);

  $("btn-chip").disabled = !game.turn.can_spend_chip;
  $("btn-chip").hidden = !game.rules.chips;
  $("btn-next").hidden = game.cards.length > 0 && !game.complete;
  $("btn-next").disabled = game.turn.rolls_used === 0;

  if (roll && roll.verdict === "void") {
    note("This roll was voided — the dice changed after they were read.", "bad");
  } else if (game.message) {
    note(game.message, "warn");
  }
}

// --- the connection ---------------------------------------------------------

function connect() {
  const socket = new WebSocket(`${location.origin.replace(/^http/, "ws")}/api/v1/events`);
  state.socket = socket;
  socket.onopen = () => { $("link-state").textContent = "watching the tray"; state.retry = 1000; };
  socket.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.error) { $("link-state").textContent = data.error; return; }
    state.last = data;
    if (data.game) render(data.game, data);
  };
  socket.onclose = () => {
    $("link-state").textContent = "reconnecting…";
    // Backing off matters here: this page is meant to be left open all evening, and a Pi
    // that is restarting should not be hammered by a television.
    setTimeout(connect, state.retry);
    state.retry = Math.min(state.retry * 2, 15000);
  };
}

$("btn-chip").onclick = () => post("/api/v1/game/chip");
$("btn-next").onclick = () => post("/api/v1/game/next");
$("btn-reset").onclick = () => {
  if (confirm("Start a new game? Scores are cleared.")) post("/api/v1/game/reset");
};

// Show whatever is already there before the first roll arrives.
fetch("/api/v1/game").then((r) => r.json()).then((data) => {
  state.last = data.last;
  render(data.game, data.last);
}).catch(() => {});
connect();
