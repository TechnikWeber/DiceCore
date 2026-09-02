/*
 * The setup page. Plain JavaScript, no framework, no build step — the whole UI is this file
 * plus one HTML file, read per request, so updating a Pi is a git pull and a restart.
 *
 * Two conventions worth knowing before editing:
 *  - Every tab is a URL (#training), so a link into a panel works and reload keeps the tab.
 *  - Every failed request is shown to the user with the server's own sentence. The API
 *    answers with prose ("no camera bound to dtoverlay=imx519"); swallowing that and
 *    printing "error" would throw away the only repair instruction there is.
 */

const $ = (id) => document.getElementById(id);
const state = { settings: null, options: null, sets: [], setId: null, ws: null, timers: {} };

// --- plumbing ---------------------------------------------------------------

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const type = response.headers.get("content-type") || "";
  const body = type.includes("json") ? await response.json() : await response.text();
  if (!response.ok || (body && body.error)) {
    throw new Error((body && (body.detail || body.error)) || `${response.status} ${response.statusText}`);
  }
  return body;
}

const json = (method, payload) => ({
  method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
});

function alertBox(message, kind = "bad") {
  const box = document.createElement("div");
  box.className = `msg ${kind}`;
  box.textContent = message;
  $("alerts").prepend(box);
  setTimeout(() => box.remove(), 9000);
}

function escapeHtml(text) {
  return String(text).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

// --- tabs -------------------------------------------------------------------

function showTab() {
  const name = (location.hash || "#roll").slice(1);
  document.querySelectorAll("section").forEach((s) => s.classList.toggle("on", s.id === name));
  document.querySelectorAll("nav a").forEach((a) => a.classList.toggle("on", a.hash === `#${name}`));
  if (name === "camera") { refreshHardware(); refreshPreview(); }
  if (name === "signals") pollOutputs();
  if (name === "detection") { pollModeSession(); renderPlayState(); refreshTrayImage(); }
  if (name === "training") { loadSets(); pollTraining(); }
  if (name === "api") pollPublish();
  if (name === "system") refreshStatus();
}
window.addEventListener("hashchange", showTab);

// --- rolling ----------------------------------------------------------------

const VERDICT_WORDS = {
  clean: "watched · untouched",
  disturbed: "disturbed — check below",
  void: "VOID — do not count this",
  pending: "not verified yet",
  unverified: "not watched",
};

function renderVerdict(result) {
  const badge = $("verdict");
  const verdict = result.verdict || "unverified";
  badge.hidden = verdict === "unverified";
  badge.className = `verdict ${verdict}`;
  badge.textContent = VERDICT_WORDS[verdict] || verdict;
  document.getElementById("roll").classList.toggle("voided", verdict === "void");

  const events = (result.integrity && result.integrity.events) || [];
  $("roll-integrity").innerHTML = events.length
    ? `<ul class="events">${events.map((e) =>
        `<li class="${escapeHtml(e.severity)}">${escapeHtml(e.detail)}</li>`).join("")}</ul>`
    : "";
}

function renderResult(result) {
  const reading = result.reading || {};
  // The mode owns the headline: "Full house" and "3 successes" are answers no generic rule
  // about totals could ever produce.
  $("total").textContent = result.count ? (reading.headline ?? result.total) : "—";
  $("notation").textContent = (reading.detail || result.notation)
    + (result.engine ? `   ·   ${result.engine}` : "")
    + (reading.mode && reading.mode !== "normal" ? `   ·   ${reading.mode}` : "");
  const chips = result.dice.map((die) => {
    const unread = die.unread;
    const weak = !unread && die.confidence < (state.settings?.engine?.min_confidence ?? 0.6);
    const label = unread ? `${die.kind} · ?` : `${die.kind} · ${die.value}`;
    const trust = unread ? "not read" : `${Math.round(die.confidence * 100)}%`;
    return `<span class="chip ${unread ? "unread" : weak ? "weak" : ""}">${label}
      <span class="muted">${trust}</span></span>`;
  });
  $("dice-chips").innerHTML = chips.join("");
  // Warnings the guard already explains as events would otherwise be printed twice.
  const events = new Set(((result.integrity && result.integrity.events) || []).map((e) => e.detail));
  $("roll-messages").innerHTML = (result.warnings || [])
    .filter((w) => !events.has(w))
    .map((w) => `<div class="msg warn">${escapeHtml(w)}</div>`).join("");
  if (result.stale) {
    $("roll-messages").innerHTML +=
      `<div class="msg warn">Nothing was thrown — these are the dice from the last reading.</div>`;
  }
  renderVerdict(result);

  const image = $("roll-image");
  image.onload = () => drawBoxes(result);
  image.src = `/api/setup/frame.jpg?t=${Date.now()}`;
}

function drawBoxes(result) {
  const frame = $("roll-frame");
  const image = $("roll-image");
  frame.querySelectorAll(".box").forEach((b) => b.remove());
  if (!image.naturalWidth) return;
  const scale = image.clientWidth / image.naturalWidth;
  for (const die of result.dice) {
    const box = document.createElement("div");
    box.className = "box";
    box.style.left = `${die.box.x * scale}px`;
    box.style.top = `${die.box.y * scale}px`;
    box.style.width = `${die.box.w * scale}px`;
    box.style.height = `${die.box.h * scale}px`;
    if (die.unread) box.classList.add("unread");
    box.innerHTML = `<b>${die.unread ? "?" : die.value}</b>`;
    frame.appendChild(box);
  }
}

async function roll(verify = true) {
  $("btn-roll").disabled = true;
  try {
    // The number goes up as soon as the dice settle; the verdict follows once the tray has
    // been watched, so the page never sits blank for the length of the hold window.
    const result = await api("/api/v1/roll?verify=0");
    renderResult(result);
    if (verify && state.settings && state.settings.guard.enabled) {
      renderResult(await api("/api/v1/verify", { method: "POST" }));
    }
  } catch (err) {
    alertBox(err.message);
  } finally {
    $("btn-roll").disabled = false;
  }
}

// --- settings ---------------------------------------------------------------

function fillSelect(select, items, selected) {
  select.innerHTML = items
    .map((i) => `<option value="${i.id}" ${i.id === selected ? "selected" : ""}>${escapeHtml(i.label)}</option>`)
    .join("");
}

//: Every assignment guarded, because the alternative bites hard: a single stale path — one
//: `s.output` left behind by a rename — threw halfway through and left every field after it
//: silently empty, which looks like a dozen unrelated bugs rather than one.
function apply(steps) {
  const failures = [];
  for (const [name, step] of Object.entries(steps)) {
    try {
      step();
    } catch (err) {
      failures.push(`${name}: ${err.message}`);
    }
  }
  if (failures.length) {
    console.error("setup form:", failures);
    alertBox(`Some settings could not be shown — ${failures[0]}`, "bad");
  }
}

function loadForm() {
  const s = state.settings;
  apply({
    mode: () => {
      fillSelect($("mode-select"), state.options.modes, s.mode.active);
      fillSelect($("mode-pick"), state.options.modes, s.mode.active);
      $("mode-d10").value = s.mode.d10_style;
      $("mode-zero").value = s.mode.d10_zero_counts_as_ten ? "ten" : "zero";
      renderModeEditor();
      renderModeBlurb();
    },
    players: () => {
      $("play-players").value = (s.play.players || []).join("\n");
    },
    camera: () => {
      fillSelect($("cap-source"), state.options.sources, s.capture.source);
      fillSelect($("csi-module"), state.options.csi_modules.map(
        (m) => ({ id: m.id, label: m.label })), s.capture.csi_module);
      $("cap-folder").value = s.capture.folder;
      $("cap-device").value = s.capture.device;
      $("cap-width").value = s.capture.width;
      $("cap-height").value = s.capture.height;
      $("cap-rotation").value = s.capture.rotation;
      $("cap-tuning").value = s.capture.tuning_file;
      $("cap-focus").value = s.capture.focus_mode;
      $("cap-dioptre").value = s.capture.focus_dioptre;
      updateCsiNote();
    },
    engine: () => {
      fillSelect($("eng-mode"), state.options.engines, s.engine.mode);
      $("eng-model").value = s.engine.model_path;
      $("eng-remote").value = s.engine.remote_url;
      $("eng-conf").value = s.engine.min_confidence;
      $("kind-checks").innerHTML = state.options.kinds.map((k) => `
        <label class="row" style="margin:0;gap:6px">
          <input type="checkbox" class="kind" value="${k.id}"
            ${s.engine.expected_kinds.includes(k.id) ? "checked" : ""}> ${k.id}
        </label>`).join("");
    },
    tray: () => {
      $("tray-x").value = s.tray.x; $("tray-y").value = s.tray.y;
      $("tray-w").value = s.tray.w; $("tray-h").value = s.tray.h;
      $("tray-mm").value = s.tray.mm_per_px;
      drawTray(trayFromSettings());
    },
    classic: () => {
      $("cl-light").checked = s.classic.dice_are_light;
      $("cl-min").value = s.classic.min_area_frac;
      $("cl-max").value = s.classic.max_area_frac;
      $("cl-blur").value = s.classic.blur;
    },
    guard: () => {
      fillSelect($("gd-policy"), state.options.policies, s.guard.policy);
      $("gd-enabled").checked = s.guard.enabled;
      $("gd-hold").value = s.guard.hold_s;
      $("gd-interval").value = s.guard.interval_s;
      $("gd-motion").value = s.guard.motion_threshold;
      $("gd-hand").value = s.guard.hand_area_frac;
      $("gd-touch").checked = s.guard.void_on_touch;
      $("gd-throw").checked = s.guard.require_throw;
    },
    settling: () => {
      $("st-enabled").checked = s.settle.enabled;
      $("st-motion").value = s.settle.motion_threshold;
      $("st-frames").value = s.settle.stable_frames;
      $("st-timeout").value = s.settle.timeout_s;
    },
    display: () => {
      fillSelect($("dp-kind"), state.options.panels, s.panel.display.kind);
      $("dp-enabled").checked = s.panel.display.enabled;
      $("dp-width").value = s.panel.display.width;
      $("dp-height").value = s.panel.display.height;
      $("dp-rotate").value = s.panel.display.rotate;
      $("dp-spiport").value = s.panel.display.spi_port;
      $("dp-spidev").value = s.panel.display.spi_device;
      $("dp-dc").value = s.panel.display.gpio_dc;
      $("dp-rst").value = s.panel.display.gpio_rst;
      $("dp-i2cport").value = s.panel.display.i2c_port;
      $("dp-i2caddr").value = s.panel.display.i2c_address;
      panelSizes();
    },
    signals: () => {
      $("sg-enabled").checked = s.panel.signals.enabled;
      $("sg-green").value = s.panel.signals.green_pin;
      $("sg-red").value = s.panel.signals.red_pin;
      $("sg-buzzer").value = s.panel.signals.buzzer_pin;
      $("sg-buzzon").checked = s.panel.signals.buzzer_enabled;
      $("sg-beep").value = s.panel.signals.beep_ms;
      $("sg-high").checked = s.panel.signals.active_high;
      $("sg-celebsound").checked = s.panel.signals.celebrate_sound;
      $("sg-chipbtn").value = s.panel.signals.chip_pin;
      $("sg-nextbtn").value = s.panel.signals.next_pin;
      $("sg-pullup").checked = s.panel.signals.button_pull_up;
      $("sg-debounce").value = s.panel.signals.debounce_s;
    },
    celebration: () => {
      $("cl-mode").value = s.panel.celebrate;
      $("cl-total").value = s.panel.celebrate_total;
      $("cl-lament").checked = s.panel.lament_on_min;
      $("cl-frames").value = s.panel.animation_frames;
    },
    publish: () => {
      const pb = s.publish;
      $("pb-enabled").checked = pb.enabled;
      $("pb-usable").checked = pb.only_usable;
      $("pb-avrae").checked = pb.avrae_enabled;
      $("pb-avrae-token").value = pb.avrae_token;
      $("pb-avrae-uvar").value = pb.avrae_uvar;
      $("pb-avrae-api").value = pb.avrae_api;
      $("pb-discord").checked = pb.discord_enabled;
      $("pb-discord-url").value = pb.discord_webhook;
      $("pb-discord-name").value = pb.discord_name;
      $("pb-webhook").checked = pb.webhook_enabled;
      $("pb-webhook-url").value = pb.webhook_url;
      $("avrae-alias").textContent = avraeAlias(pb.avrae_uvar || "dicecore");
    },
    server: () => {
      $("sv-stream").checked = s.server.stream_enabled;
      $("sv-fps").value = s.server.stream_fps;
    },
    summary: () => {
      $("settings-dump").textContent = JSON.stringify(s, null, 2);
      $("subtitle").textContent =
        `${s.server.public_name} · ${s.capture.source} → ${s.engine.mode}`
        + (s.guard.enabled ? ` · fair play: ${s.guard.policy}` : "");
    },
  });
}

function collectForm() {
  const s = structuredClone(state.settings);
  s.capture.source = $("cap-source").value;
  s.capture.folder = $("cap-folder").value;
  s.capture.device = Number($("cap-device").value);
  s.capture.width = Number($("cap-width").value);
  s.capture.height = Number($("cap-height").value);
  s.capture.rotation = Number($("cap-rotation").value);
  s.capture.tuning_file = $("cap-tuning").value;
  s.capture.focus_mode = $("cap-focus").value;
  s.capture.focus_dioptre = Number($("cap-dioptre").value);
  s.engine.mode = $("eng-mode").value;
  s.engine.model_path = $("eng-model").value;
  s.engine.remote_url = $("eng-remote").value;
  s.engine.min_confidence = Number($("eng-conf").value);
  s.engine.expected_kinds = [...document.querySelectorAll(".kind:checked")].map((c) => c.value);
  s.tray.x = Number($("tray-x").value); s.tray.y = Number($("tray-y").value);
  s.tray.w = Number($("tray-w").value); s.tray.h = Number($("tray-h").value);
  s.tray.mm_per_px = Number($("tray-mm").value);
  s.classic.dice_are_light = $("cl-light").checked;
  s.classic.min_area_frac = Number($("cl-min").value);
  s.classic.max_area_frac = Number($("cl-max").value);
  s.classic.blur = Number($("cl-blur").value);
  s.guard.enabled = $("gd-enabled").checked;
  s.guard.policy = $("gd-policy").value;
  s.guard.hold_s = Number($("gd-hold").value);
  s.guard.interval_s = Number($("gd-interval").value);
  s.guard.motion_threshold = Number($("gd-motion").value);
  s.guard.hand_area_frac = Number($("gd-hand").value);
  s.guard.void_on_touch = $("gd-touch").checked;
  s.guard.require_throw = $("gd-throw").checked;
  s.panel.display.enabled = $("dp-enabled").checked;
  s.panel.display.kind = $("dp-kind").value;
  s.panel.display.width = Number($("dp-width").value);
  s.panel.display.height = Number($("dp-height").value);
  s.panel.display.rotate = Number($("dp-rotate").value);
  s.panel.display.spi_port = Number($("dp-spiport").value);
  s.panel.display.spi_device = Number($("dp-spidev").value);
  s.panel.display.gpio_dc = Number($("dp-dc").value);
  s.panel.display.gpio_rst = Number($("dp-rst").value);
  s.panel.display.i2c_port = Number($("dp-i2cport").value);
  s.panel.display.i2c_address = $("dp-i2caddr").value;
  s.panel.signals.enabled = $("sg-enabled").checked;
  s.panel.signals.green_pin = Number($("sg-green").value);
  s.panel.signals.red_pin = Number($("sg-red").value);
  s.panel.signals.buzzer_pin = Number($("sg-buzzer").value);
  s.panel.signals.buzzer_enabled = $("sg-buzzon").checked;
  s.panel.signals.beep_ms = Number($("sg-beep").value);
  s.panel.signals.active_high = $("sg-high").checked;
  s.panel.signals.celebrate_sound = $("sg-celebsound").checked;
  s.panel.celebrate = $("cl-mode").value;
  s.panel.celebrate_total = Number($("cl-total").value);
  s.panel.lament_on_min = $("cl-lament").checked;
  s.panel.animation_frames = Number($("cl-frames").value);
  s.panel.signals.chip_pin = Number($("sg-chipbtn").value);
  s.panel.signals.next_pin = Number($("sg-nextbtn").value);
  s.panel.signals.button_pull_up = $("sg-pullup").checked;
  s.panel.signals.debounce_s = Number($("sg-debounce").value);
  s.publish.enabled = $("pb-enabled").checked;
  s.publish.only_usable = $("pb-usable").checked;
  s.publish.avrae_enabled = $("pb-avrae").checked;
  s.publish.avrae_token = $("pb-avrae-token").value.trim();
  s.publish.avrae_uvar = $("pb-avrae-uvar").value.trim() || "dicecore";
  s.publish.avrae_api = $("pb-avrae-api").value.trim();
  s.publish.discord_enabled = $("pb-discord").checked;
  s.publish.discord_webhook = $("pb-discord-url").value.trim();
  s.publish.discord_name = $("pb-discord-name").value.trim() || "DiceCore";
  s.publish.webhook_enabled = $("pb-webhook").checked;
  s.publish.webhook_url = $("pb-webhook-url").value.trim();
  s.server.stream_enabled = $("sv-stream").checked;
  s.server.stream_fps = Number($("sv-fps").value);
  s.settle.enabled = $("st-enabled").checked;
  s.settle.motion_threshold = Number($("st-motion").value);
  s.settle.stable_frames = Number($("st-frames").value);
  s.settle.timeout_s = Number($("st-timeout").value);
  return s;
}

async function saveSettings() {
  try {
    const answer = await api("/api/setup/settings", json("PUT", collectForm()));
    state.settings = answer.settings;
    loadForm();
    refreshStatus();
    alertBox("Saved.", "good");
  } catch (err) {
    alertBox(err.message);
  }
}

function updateCsiNote() {
  const module = state.options.csi_modules.find((m) => m.id === $("csi-module").value);
  $("csi-note").textContent = module ? module.note : "";
  $("csi-custom-wrap").hidden = $("csi-module").value !== "custom";
}

async function applyModule() {
  try {
    const answer = await api("/api/setup/camera-module",
      json("POST", { module: $("csi-module").value, overlay: $("csi-custom").value }));
    alertBox(`Written to ${answer.path}. Reboot for it to take effect.`, "warn");
    if (answer.tuning_file) $("cap-tuning").value = answer.tuning_file;
  } catch (err) {
    alertBox(err.message);
  }
}

// --- hardware / status ------------------------------------------------------

// --- the tray, drawn rather than typed --------------------------------------

function trayFromSettings() {
  const t = state.settings.tray;
  return { x: t.x, y: t.y, w: t.w, h: t.h };
}

function drawTray(box) {
  const sel = $("tray-sel");
  sel.hidden = false;
  sel.style.left = `${box.x * 100}%`;
  sel.style.top = `${box.y * 100}%`;
  sel.style.width = `${box.w * 100}%`;
  sel.style.height = `${box.h * 100}%`;
  $("tray-readout").textContent =
    `x ${box.x.toFixed(2)} · y ${box.y.toFixed(2)} · w ${box.w.toFixed(2)} · h ${box.h.toFixed(2)}`;
  $("tray-x").value = box.x.toFixed(3);
  $("tray-y").value = box.y.toFixed(3);
  $("tray-w").value = box.w.toFixed(3);
  $("tray-h").value = box.h.toFixed(3);
}

function setupTrayEditor() {
  const view = $("tray-view");
  let start = null;

  const at = (event) => {
    const rect = view.getBoundingClientRect();
    return {
      x: Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width)),
      y: Math.min(1, Math.max(0, (event.clientY - rect.top) / rect.height)),
    };
  };

  view.addEventListener("pointerdown", (event) => {
    start = at(event);
    view.setPointerCapture(event.pointerId);
  });
  view.addEventListener("pointermove", (event) => {
    if (!start) return;
    const now = at(event);
    drawTray({
      x: Math.min(start.x, now.x), y: Math.min(start.y, now.y),
      w: Math.abs(now.x - start.x), h: Math.abs(now.y - start.y),
    });
  });
  view.addEventListener("pointerup", (event) => {
    if (!start) return;
    const now = at(event);
    // A tap rather than a drag means "no change" — dragging a zero-sized tray by accident
    // would blind the engine completely.
    if (Math.abs(now.x - start.x) > 0.02 && Math.abs(now.y - start.y) > 0.02) {
      drawTray({
        x: Math.min(start.x, now.x), y: Math.min(start.y, now.y),
        w: Math.abs(now.x - start.x), h: Math.abs(now.y - start.y),
      });
    } else {
      drawTray(trayFromSettings());
    }
    start = null;
    view.releasePointerCapture(event.pointerId);
  });
}

function refreshTrayImage() {
  $("tray-image").src = `/api/setup/preview.jpg?t=${Date.now()}`;
}

function refreshPreview() {
  $("preview-image").src = `/api/setup/preview.jpg?t=${Date.now()}`;
}

async function refreshHardware() {
  try {
    const hw = await api("/api/setup/hardware");
    const rows = [
      ["Camera tool", hw.tool || "none found"],
      ["CSI cameras", hw.csi.length ? hw.csi.join("<br>") : "none"],
      ["Video nodes", hw.video_nodes.join(", ") || "none"],
    ];
    $("hardware").innerHTML =
      `<table>${rows.map(([k, v]) => `<tr><th>${k}</th><td>${v}</td></tr>`).join("")}</table>`
      + (hw.problem ? `<div class="msg warn" style="margin-top:10px">${escapeHtml(hw.problem)}</div>` : "")
      + (hw.boot_advice ? `<div class="msg warn">${escapeHtml(hw.boot_advice)}</div>` : "");
  } catch (err) {
    $("hardware").innerHTML = `<div class="msg bad">${escapeHtml(err.message)}</div>`;
  }
}

async function refreshStatus() {
  try {
    const status = await api("/api/setup/status");
    const c = status.capabilities;
    const yes = (v) => (v ? "yes" : "no");
    $("capabilities").innerHTML = `<table>
      <tr><th>Machine</th><td>${escapeHtml(c.pi || c.machine)}</td></tr>
      <tr><th>Read pips (numpy + OpenCV)</th><td>${yes(c.can_run_classic)}</td></tr>
      <tr><th>Run a trained model (onnxruntime)</th><td>${yes(c.can_run_model)}</td></tr>
      <tr><th>Train a model (PyTorch)</th><td>${yes(c.can_train)}</td></tr>
      <tr><th>Boot config</th><td>${escapeHtml(status.boot.path || "not a Pi")} —
        module <code>${escapeHtml(status.boot.module)}</code></td></tr>
    </table>` + c.advice.map((a) => `<div class="msg warn" style="margin-top:8px">${escapeHtml(a)}</div>`).join("");
    $("config-path").textContent = status.config_path;
    (status.reader.problems || []).forEach((p) => alertBox(p, "warn"));
  } catch (err) {
    alertBox(err.message);
  }
}

// --- dataset & labelling ----------------------------------------------------

async function loadSets() {
  try {
    state.sets = await api("/api/setup/sets");
  } catch (err) {
    alertBox(err.message);
    return;
  }
  if (!state.setId && state.sets.length) state.setId = state.sets[0].id;
  // An empty <select> is a blank box that tells you nothing — broken and empty look the
  // same. Say which it is, and switch off the buttons that need a set to work.
  const empty = !state.sets.length;
  $("set-select").innerHTML = empty
    ? `<option value="">No sets yet — press “New set”</option>`
    : state.sets.map((s) => `<option value="${s.id}" ${s.id === state.setId ? "selected" : ""}
        >${escapeHtml(s.name)} (${s.stats.confirmed_dice} dice)</option>`).join("");
  $("set-select").disabled = empty;
  $("btn-capture").disabled = empty;
  $("auto-capture").disabled = empty;
  if (empty) $("auto-capture").checked = false;
  renderSetStats();
  loadSamples();
}

function renderSetStats() {
  const set = state.sets.find((s) => s.id === state.setId);
  if (!set) {
    $("set-stats").innerHTML = `<div class="msg warn">
      <b>No set yet.</b> A set is one lot of dice photographed under one light — name it
      after both (“black d20s, desk lamp”), because a model trained across two different
      setups learns the average of them and is worse at each. Press <b>New set</b> to start
      one.</div>`;
    return;
  }
  const r = set.readiness;
  const classes = Object.entries(r.classes)
    .map(([k, v]) => `<span class="chip ${v < 10 ? "weak" : ""}">${k} <span class="muted">${v}</span></span>`)
    .join("");
  $("set-stats").innerHTML = `
    <div class="spread"><b>${escapeHtml(set.name)}</b>
      <span class="muted">${set.stats.frames} rolls · ${set.stats.confirmed_dice} confirmed dice
      ${set.stats.engine_agreement !== null ? `· engine agrees ${Math.round(set.stats.engine_agreement * 100)}%` : ""}</span></div>
    <div class="chips">${classes || '<span class="muted">nothing confirmed yet</span>'}</div>
    ${r.reasons.map((x) => `<div class="msg warn" style="margin-top:8px">${escapeHtml(x)}</div>`).join("")}`;
}

async function loadSamples() {
  if (!state.setId) { $("samples").innerHTML = ""; return; }
  let samples;
  try {
    samples = await api(`/api/setup/sets/${state.setId}/samples?limit=40`);
  } catch (err) { alertBox(err.message); return; }

  if (!samples.length) {
    $("samples").innerHTML = `<p class="muted">Nothing stored yet — press
      <b>Roll and store</b> and the throws will appear here to be confirmed.</p>`;
    return;
  }
  $("samples").innerHTML = samples.map((sample) => {
    const dice = sample.dice.map((die, index) => {
      const kinds = state.options.kinds
        .map((k) => `<option ${k.id === die.kind ? "selected" : ""}>${k.id}</option>`).join("");
      const values = (state.options.kinds.find((k) => k.id === die.kind) || { values: [] }).values
        .map((v) => `<option ${v === die.value ? "selected" : ""}>${v}</option>`).join("");
      return `<span class="chip" data-index="${index}">
        <select class="k">${kinds}</select>
        <select class="v">${die.unread ? '<option selected>?</option>' : ""}${values}</select>
      </span>`;
    }).join("");
    return `<div class="sample" data-id="${sample.id}">
      <img loading="lazy" src="/api/setup/sets/${state.setId}/samples/${sample.id}.jpg">
      <div class="dice">${dice || '<span class="muted">no dice found</span>'}</div>
      <div class="row" style="margin-top:8px">
        <button class="primary confirm">${sample.dice.every((d) => d.confirmed) ? "Confirmed ✓" : "Confirm"}</button>
        <button class="danger drop">Delete</button>
      </div>
    </div>`;
  }).join("");

  $("samples").querySelectorAll(".sample").forEach((node) => {
    node.querySelector(".confirm").onclick = () => confirmSample(node);
    node.querySelector(".drop").onclick = () => dropSample(node);
    // Changing the kind changes which values exist — a d6 has no 14.
    node.querySelectorAll(".k").forEach((select) => {
      select.onchange = () => {
        const values = state.options.kinds.find((k) => k.id === select.value).values;
        select.parentElement.querySelector(".v").innerHTML =
          values.map((v) => `<option>${v}</option>`).join("");
      };
    });
  });
}

async function confirmSample(node) {
  const dice = [...node.querySelectorAll(".chip")].map((chip) => ({
    kind: chip.querySelector(".k").value,
    value: Number(chip.querySelector(".v").value),
    confirmed: true,
  }));
  if (dice.some((d) => Number.isNaN(d.value))) { alertBox("Pick a value for every die first."); return; }
  try {
    await api(`/api/setup/sets/${state.setId}/samples/${node.dataset.id}`, json("PATCH", { dice }));
    await loadSets();
  } catch (err) { alertBox(err.message); }
}

async function dropSample(node) {
  try {
    await api(`/api/setup/sets/${state.setId}/samples/${node.dataset.id}`, { method: "DELETE" });
    await loadSets();
  } catch (err) { alertBox(err.message); }
}

async function captureIntoSet() {
  if (!state.setId) { alertBox("Create a set first."); return; }
  try {
    const answer = await api(`/api/setup/sets/${state.setId}/capture`, { method: "POST" });
    renderResult(answer.result);
    await loadSets();
  } catch (err) { alertBox(err.message); }
}

// --- training ---------------------------------------------------------------

// --- installing the optional halves from here -------------------------------

function renderInstall(extras) {
  const missing = Object.entries(extras).filter(([, e]) => !e.installed);
  const job = state.install;
  const busy = job && job.state === "running";

  $("install-panel").innerHTML = `
    ${missing.length ? `<p class="hint">Not installed on this machine yet. The button
      does what a terminal would — <code>pip install</code> into this virtualenv — and
      DiceCore has to be restarted afterwards to pick it up.</p>
      <div class="row">${missing.map(([key, e]) =>
        `<button data-install="${key}" ${busy ? "disabled" : ""}>${escapeHtml(e.why)}</button>`)
        .join("")}</div>`
      : `<p class="muted">Everything optional is installed on this machine.</p>`}
    ${job ? `<div class="msg ${job.state === "failed" ? "bad"
        : job.state === "done" ? "good" : "warn"}" style="margin-top:10px">
        ${escapeHtml(job.extra)}: ${escapeHtml(job.state)} · ${job.elapsed_s}s
        ${job.error ? `— ${escapeHtml(job.error)}` : ""}</div>
      <pre style="max-height:200px">${escapeHtml((job.lines || []).join("\n"))}</pre>` : ""}`;

  $("install-panel").querySelectorAll("[data-install]").forEach((button) => {
    button.onclick = async () => {
      try {
        state.install = await api("/api/setup/install",
                                  json("POST", { extra: button.dataset.install }));
        pollInstall();
      } catch (err) { alertBox(err.message); }
    };
  });
}

async function pollInstall() {
  let info;
  try { info = await api("/api/setup/install"); } catch { return; }
  state.install = info.job;
  renderInstall(info.extras);
  clearTimeout(state.timers.install);
  // PyTorch is two gigabytes: check often enough to look alive, rarely enough to be quiet.
  if (info.running) state.timers.install = setTimeout(pollInstall, 1500);
}

async function pollTraining() {
  let info;
  try { info = await api("/api/setup/training"); } catch { return; }
  $("train-availability").innerHTML = info.available
    ? ""
    : `<div class="msg warn">${escapeHtml(info.why)}</div>`;
  $("btn-train").disabled = !info.available;
  renderInstall(info.extras || {});

  const job = info.job;
  if (job) {
    const p = job.progress || {};
    const done = p.epoch ? Math.round((p.epoch / (p.epochs || 1)) * 100) : (job.state === "done" ? 100 : 0);
    $("train-progress").innerHTML = `
      <div class="spread"><b>${escapeHtml(job.state)}</b>
        <span class="muted">${escapeHtml(p.message || `epoch ${p.epoch || 0}/${p.epochs || job.epochs}`)}
        ${p.accuracy !== undefined ? `· accuracy ${Math.round(p.accuracy * 100)}%` : ""}
        ${p.loss !== undefined ? `· loss ${p.loss}` : ""} · ${job.elapsed_s}s</span></div>
      <div class="bar" style="margin-top:8px"><i style="width:${done}%"></i></div>
      ${job.error ? `<div class="msg bad" style="margin-top:8px">${escapeHtml(job.error)}</div>` : ""}`;
  }
  $("models").innerHTML = info.models.length
    ? `<table><tr><th>Model</th><th>Accuracy</th><th>Dice</th><th>Faces</th><th></th></tr>` +
      info.models.map((m) => `<tr>
        <td><code>${escapeHtml(m.name)}</code></td>
        <td>${m.accuracy !== null && m.accuracy !== undefined ? Math.round(m.accuracy * 100) + "%" : "—"}</td>
        <td>${m.samples ?? "—"}</td><td>${m.classes}</td>
        <td><button data-use="${escapeHtml(m.path)}">Use</button></td></tr>`).join("") + "</table>"
    : `<p class="muted">No models yet. Collect a set, then train.</p>`;
  $("models").querySelectorAll("[data-use]").forEach((button) => {
    button.onclick = async () => {
      try {
        await api("/api/setup/training/use", json("POST", { path: button.dataset.use }));
        await boot();
        alertBox("Engine switched to that model.", "good");
      } catch (err) { alertBox(err.message); }
    };
  });

  clearTimeout(state.timers.training);
  if (location.hash === "#training") {
    state.timers.training = setTimeout(pollTraining, job && job.state === "running" ? 1500 : 6000);
  }
}

// --- game modes -------------------------------------------------------------

function modeById(id) {
  return state.options.modes.find((m) => m.id === id);
}

function renderModeBlurb() {
  const mode = modeById($("mode-pick").value);
  $("mode-blurb").textContent = mode ? `${mode.blurb} (${mode.dice} dice)` : "";
}

function renderModeEditor() {
  const mode = modeById($("mode-select").value);
  if (!mode) return;
  $("mode-detail").textContent =
    `${mode.blurb}  Dice: ${mode.dice} of ${mode.kinds.join(", ")}.`;

  // Built from the mode's own defaults, so a new mode needs no UI work at all.
  const saved = (state.settings.mode.params || {})[mode.id] || {};
  const choices = {
    rule: ["sum", "pool", "best", "under"],
    take: ["high", "low"],
  };
  // Offered on every mode, not only the ones that declare it: what a zero on a 0-9
  // ten-sider is worth is a per-game house rule, and the general setting is the fallback
  // rather than the law.
  const zero = saved.zero_is_ten;
  const zeroRow = `<div><label>a zero on a 0–9 die counts as</label>
    <select class="mp" data-key="zero_is_ten">
      <option value="" ${zero === undefined ? "selected" : ""}>as set generally
        (${state.settings.mode.d10_zero_counts_as_ten ? "ten" : "nothing"})</option>
      <option value="true" ${zero === true ? "selected" : ""}>ten</option>
      <option value="false" ${zero === false ? "selected" : ""}>nothing — a 0 is a 0</option>
    </select></div>`;
  $("mode-params").innerHTML = Object.entries(mode.defaults).map(([key, fallback]) => {
    const value = key in saved ? saved[key] : fallback;
    const label = escapeHtml(key.replace(/_/g, " "));
    if (typeof fallback === "boolean") {
      return `<div><label>${label}</label><input class="mp" data-key="${key}" type="checkbox"
        ${value ? "checked" : ""}></div>`;
    }
    if (key === "chips") {
      return `<div><label>${label}</label><select class="mp" data-key="chips">${
        [0, 1, 2, 3, 4].map((n) =>
          `<option ${n === Number(value) ? "selected" : ""}>${n}</option>`).join("")
      }</select></div>`;
    }
    if (choices[key]) {
      return `<div><label>${label}</label><select class="mp" data-key="${key}">${
        choices[key].map((o) => `<option ${o === value ? "selected" : ""}>${o}</option>`).join("")
      }</select></div>`;
    }
    return `<div><label>${label}</label><input class="mp" data-key="${key}" type="number"
      value="${escapeHtml(value)}"></div>`;
  }).join("") + zeroRow;
}

function collectModeParams() {
  const params = {};
  document.querySelectorAll(".mp").forEach((el) => {
    if (el.dataset.key === "zero_is_ten") {
      // An empty choice means "inherit", and inheriting has to be expressible — so the key
      // is left out rather than sent as a value the mode would then be stuck with.
      if (el.value !== "") params.zero_is_ten = el.value === "true";
      return;
    }
    params[el.dataset.key] = el.type === "checkbox" ? el.checked
      : el.tagName === "SELECT" ? el.value : Number(el.value);
  });
  return params;
}

async function saveMode(id, params) {
  try {
    await api("/api/setup/mode", json("POST", {
      mode: id, params, d10_style: $("mode-d10").value,
      d10_zero_counts_as_ten: $("mode-zero").value === "ten",
    }));
    await boot();
    alertBox("Mode saved.", "good");
  } catch (err) { alertBox(err.message); }
}

async function renderPlayState() {
  try {
    const info = await api("/api/v1/game");
    const game = info.game;
    const turn = game.turn;
    $("play-state").innerHTML = game.rules.multi
      ? `<p class="muted">${escapeHtml(game.current_player)} — throw ${turn.rolls_used}
         of ${turn.rolls_allowed}, turn ${turn.number}
         ${turn.chips_left ? `· ${turn.chips_left} chip(s) left` : ""}</p>`
      : `<p class="muted">${escapeHtml(game.mode)} plays one throw a turn — nothing to
         count down.</p>`;
  } catch { $("play-state").innerHTML = ""; }
}

async function pollModeSession() {
  const mode = modeById(state.settings.mode.active);
  if (!mode || !mode.stateful) { $("mode-session").innerHTML = ""; return; }
  try {
    const last = await api("/api/v1/state");
    const extras = (last.reading && last.reading.extras) || {};
    if (extras.wording) {
      $("mode-session").innerHTML =
        `<div class="msg ${extras.state === "nothing unusual" ? "good" : "warn"}">`
        + `${escapeHtml(extras.wording)}</div>`
        + `<p class="muted">${Object.entries(extras.counts || {})
             .map(([face, n]) => `${face}: ${n}`).join(" · ")}</p>`;
    } else if (extras.open) {
      $("mode-session").innerHTML =
        `<div class="msg warn">${extras.total} so far — a die is showing its maximum, throw again.</div>`;
    } else {
      $("mode-session").innerHTML = "";
    }
  } catch { /* nothing read yet */ }
}

// --- screen and lamps -------------------------------------------------------

function panelSizes() {
  const panel = state.options.panels.find((p) => p.id === $("dp-kind").value);
  const sizes = (panel && panel.sizes) || [];
  const current = `${$("dp-width").value}x${$("dp-height").value}`;
  $("dp-size").innerHTML = [`<option value="0x0">custom / panel default</option>`]
    .concat(sizes.map(([w, h]) =>
      `<option value="${w}x${h}" ${`${w}x${h}` === current ? "selected" : ""}>${w} × ${h}</option>`))
    .join("");
  // A panel on I2C has no DC or reset pin, and one on SPI has no address; showing both
  // sets invites wiring to the wrong half.
  $("dp-spi").hidden = !panel || panel.bus !== "spi";
  $("dp-i2c").hidden = !panel || panel.bus !== "i2c";
}

async function pollOutputs() {
  let info;
  try { info = await api("/api/setup/outputs"); } catch { return; }

  const signals = info.signals;
  const lamp = (cls, on, label) =>
    `<span class="lamp ${cls} ${on ? "on" : ""}"><i></i>${escapeHtml(label)}</span>`;
  $("lamp-state").innerHTML = [
    lamp("green", signals && signals.green.on, signals ? `green — throw (pin ${signals.green.pin})` : "lamps off"),
    lamp("red", signals && signals.red.on, signals ? `red — hands off (pin ${signals.red.pin})` : ""),
    `<span class="muted">phase: <b>${escapeHtml(info.state.phase)}</b>`
      + (signals && signals.buzzer.last ? ` · buzzer: ${escapeHtml(signals.buzzer.last)}` : "")
      + (info.display ? ` · ${escapeHtml(info.display.label)} ${info.display.width}×${info.display.height}`
         + (info.display.attached ? " (attached)" : " (preview only)") : "")
      + `</span>`,
  ].join("");

  const problems = (info.problems || [])
    .concat([info.display && info.display.problem, signals && signals.problem].filter(Boolean));
  if (problems.length) {
    $("lamp-state").innerHTML +=
      problems.map((p) => `<div class="msg warn" style="width:100%">${escapeHtml(p)}</div>`).join("");
  }
  if (info.display) $("display-preview").src = `/api/setup/display.png?t=${Date.now()}`;

  clearTimeout(state.timers.outputs);
  if (location.hash === "#signals") state.timers.outputs = setTimeout(pollOutputs, 900);
}

async function testOutputs(phase) {
  try {
    await api("/api/setup/outputs/test", json("POST", phase ? { phase } : {}));
    pollOutputs();
  } catch (err) { alertBox(err.message); }
}

// --- sending rolls out ------------------------------------------------------

//: The alias a player pastes into Discord once. Written in Draconic without f-strings or
//: anything clever, because the point is that it works the first time on somebody else's
//: Avrae rather than that it is elegant.
function avraeAlias(uvar) {
  return [
    `!alias phys echo <drac2>`,
    `if not uvar_exists("${uvar}"):`,
    `    return "No physical roll yet — throw the dice."`,
    `r = load_json(get_uvar("${uvar}"))`,
    `faces = ", ".join([str(d["kind"]) + " " + str(d["value"]) for d in r["dice"]])`,
    `out = "**" + str(r["total"]) + "**  (" + faces + ")"`,
    `if not r["usable"]:`,
    `    out = out + "  ⚠️ voided — the dice changed after they were read"`,
    `return out`,
    `</drac2>`,
  ].join("\n");
}

async function pollPublish() {
  let info;
  try { info = await api("/api/setup/publish"); } catch { return; }
  const rows = info.log.slice(0, 6).map((entry) =>
    `<div>${entry.ok ? "✓" : "✗"} ${escapeHtml(entry.target)} — ${escapeHtml(entry.detail)}</div>`);
  $("publish-state").innerHTML = info.enabled
    ? (rows.length ? `<div class="muted">${rows.join("")}</div>`
       : `<p class="muted">Nothing sent yet.</p>`)
    : `<p class="muted">Sending is switched off.</p>`;
}

// --- API tab ----------------------------------------------------------------

function renderApiExamples() {
  const base = location.origin;
  $("api-examples").textContent = [
    `# read the dice now (waits for them to settle)`,
    `curl ${base}/api/v1/roll`,
    ``,
    `# the last result, without touching the camera`,
    `curl ${base}/api/v1/state`,
    ``,
    `# read an image captured somewhere else`,
    `curl -F image=@roll.jpg ${base}/api/v1/detect`,
    ``,
    `# take the number now, collect the fair-play verdict afterwards`,
    `curl "${base}/api/v1/roll?verify=0" && curl -X POST ${base}/api/v1/verify`,
    ``,
    `# from Python`,
    `import requests`,
    `roll = requests.get("${base}/api/v1/roll").json()`,
    `if roll["usable"]:            # false only for verdict == "void"`,
    `    print(roll["total"], roll["notation"], roll["verdict"])`,
  ].join("\n");
}

function toggleWebsocket() {
  if (state.ws) { state.ws.close(); state.ws = null; return; }
  const url = `${location.origin.replace(/^http/, "ws")}/api/v1/events`;
  const socket = new WebSocket(url);
  state.ws = socket;
  $("ws-state").textContent = "connecting…";
  $("btn-ws").textContent = "Disconnect";
  socket.onopen = () => ($("ws-state").textContent = "connected");
  socket.onmessage = (event) => {
    const data = JSON.parse(event.data);
    $("ws-log").textContent = JSON.stringify(data, null, 2);
    if (!data.error) renderResult(data);
  };
  socket.onclose = () => {
    $("ws-state").textContent = "not connected";
    $("btn-ws").textContent = "Connect";
    state.ws = null;
  };
}

// --- boot -------------------------------------------------------------------

async function boot() {
  state.options = await api("/api/setup/options");
  state.settings = await api("/api/setup/settings");
  loadForm();
  renderApiExamples();
  showTab();
  refreshStatus();
}

document.querySelectorAll("[data-save]").forEach((b) => (b.onclick = saveSettings));
$("btn-roll").onclick = roll;
$("btn-preview").onclick = refreshPreview;
$("btn-hardware").onclick = refreshHardware;
$("btn-tray-refresh").onclick = refreshTrayImage;
$("btn-tray-all").onclick = () => drawTray({ x: 0, y: 0, w: 1, h: 1 });
setupTrayEditor();
$("btn-module").onclick = applyModule;
$("csi-module").addEventListener("change", updateCsiNote);
$("btn-capture").onclick = captureIntoSet;
$("set-select").onchange = () => { state.setId = $("set-select").value; renderSetStats(); loadSamples(); };
$("btn-new-set").onclick = async () => {
  const name = prompt("Name this set — the dice, the light, the tower. \"black d20s, desk lamp\"");
  if (!name) return;
  try {
    const set = await api("/api/setup/sets", json("POST", { name }));
    state.setId = set.id;
    await loadSets();
  } catch (err) { alertBox(err.message); }
};
$("btn-train").onclick = async () => {
  try {
    await api("/api/setup/training/start",
      json("POST", { set_id: state.setId, epochs: Number($("train-epochs").value) }));
    pollTraining();
  } catch (err) { alertBox(err.message); }
};
$("btn-train-stop").onclick = () => api("/api/setup/training/stop", { method: "POST" }).catch(() => {});
$("btn-ws").onclick = toggleWebsocket;
$("btn-copy-alias").onclick = async () => {
  try {
    await navigator.clipboard.writeText($("avrae-alias").textContent);
    alertBox("Alias copied — paste it into Discord once.", "good");
  } catch {
    alertBox("Could not reach the clipboard; select the text and copy it.", "warn");
  }
};
$("btn-publish-test").onclick = async () => {
  try {
    const answer = await api("/api/setup/publish/test", json("POST", {}));
    for (const attempt of answer.attempts) {
      alertBox(`${attempt.target}: ${attempt.ok ? "delivered" : attempt.detail}`,
               attempt.ok ? "good" : "bad");
    }
    pollPublish();
  } catch (err) { alertBox(err.message); }
};
$("pb-avrae-uvar").addEventListener("input", () => {
  $("avrae-alias").textContent = avraeAlias($("pb-avrae-uvar").value.trim() || "dicecore");
});
$("mode-select").addEventListener("change", renderModeEditor);
$("btn-players").onclick = async () => {
  const players = $("play-players").value.split("\n").map((n) => n.trim()).filter(Boolean);
  try {
    await api("/api/v1/game/reset", json("POST", { players: players.length ? players : ["Player 1"] }));
    await boot();
    renderPlayState();
    alertBox("New game started.", "good");
  } catch (err) { alertBox(err.message); }
};
$("btn-mode-save").onclick = () => saveMode($("mode-select").value, collectModeParams());
$("btn-mode-reset").onclick = async () => {
  try {
    await api("/api/setup/mode/reset", { method: "POST" });
    pollModeSession();
    alertBox("Started again.", "good");
  } catch (err) { alertBox(err.message); }
};
// The picker on the Roll tab switches the game outright — that is where you are standing
// when you notice you are playing something else.
$("mode-pick").onchange = () => saveMode($("mode-pick").value, null);
$("dp-kind").addEventListener("change", panelSizes);
$("dp-size").addEventListener("change", () => {
  const [w, h] = $("dp-size").value.split("x").map(Number);
  $("dp-width").value = w;
  $("dp-height").value = h;
});
$("btn-test-walk").onclick = () => testOutputs(null);
document.querySelectorAll("[data-phase]").forEach((b) => (b.onclick = () => testOutputs(b.dataset.phase)));
$("live").onchange = (event) => {
  clearInterval(state.timers.live);
  // Live view is a display, not a referee: it takes the number and skips the hold window.
  if (event.target.checked) state.timers.live = setInterval(() => roll(false), 1200);
};
$("auto-capture").onchange = (event) => {
  clearInterval(state.timers.capture);
  if (event.target.checked) state.timers.capture = setInterval(captureIntoSet, 2500);
};

boot().catch((err) => alertBox(`Could not load the page: ${err.message}`));
