"use strict";
// Table page: play (you're in seat 0) or watch (bots only). Polls /api/state.

const SUIT = { s: "♠", h: "♥", d: "♦", c: "♣" };
const RANK = { T: "10" };

let S = null;          // latest state
let lastRev = -1;
const memo = {};       // region -> last html, so we only touch the DOM on change

function setHTML(id, html) {
  if (memo[id] === html) return false;
  memo[id] = html;
  $(id).innerHTML = html;
  return true;
}

const isWatch = () => S && S.mode === "watch";
const H = () => S.human_seat;                     // null in watch mode
const nameOf = (s) => (s === H() ? "You" : S.players[s].name);

// ---------------- cards & geometry ----------------

function cardHTML(c, cls = "") {
  if (!c || c === "??") return `<div class="card back ${cls}"></div>`;
  const r = RANK[c[0]] || c[0], s = c[1];
  const red = s === "h" || s === "d" ? "red" : "";
  return `<div class="card ${red} ${cls}" title="${c}"><span class="r">${r}</span><span class="s">${SUIT[s]}</span></div>`;
}

/** Position on the table ellipse. Index 0 sits at the bottom; seats run clockwise. */
function seatPos(i, n, rx, ry, offsetDeg = 0) {
  const a = (90 + (i * 360) / n + offsetDeg) * Math.PI / 180;
  return { left: 50 + rx * Math.cos(a), top: 50 + ry * Math.sin(a) };
}

// ---------------- render ----------------

function render() {
  if (!S) return;
  if (S.status === "no_game") {
    setHTML("seats", ""); setHTML("bets", ""); setHTML("pot", ""); setHTML("banner", "");
    setHTML("board", Array.from({ length: 5 }, () => `<div class="slot"></div>`).join(""));
    memo.barKey = "none";
    $("actionBar").innerHTML = `<div class="status">No game running.</div>
      <a class="btn primary" href="/#play">Play</a><a class="btn" href="/#watch">Watch bots</a>`;
    return;
  }
  document.body.classList.toggle("watching", isWatch());
  renderMeta();
  renderTable();
  renderActionBar();
  renderSide();
}

function renderMeta() {
  const b = S.blinds;
  setHTML("meta", `
    <span class="mode-pill">${isWatch() ? "Watching" : "Playing"}</span>
    <span>Hand <b class="num">${S.hand_number}</b> / ${S.num_hands}</span>
    ${b ? `<span>Blinds <b class="num">${fmt(b[0])}/${fmt(b[1])}</b>${b[2] ? ` ante <b class="num">${fmt(b[2])}</b>` : ""}</span>` : ""}
    ${S.street ? `<span>${S.street[0].toUpperCase() + S.street.slice(1)}</span>` : ""}`);
  $("reveal").checked = S.reveal;
  $("autonext").checked = S.auto_next;
  if (document.activeElement !== $("speed")) $("speed").value = S.speed;
}

function renderTable() {
  const n = S.players.length;
  const base = H() ?? 0;
  const slot = (seat) => (seat - base + n) % n;

  const seats = S.players.map((p) => {
    const pos = seatPos(slot(p.seat), n, 45, 41);
    const cls = ["seat", p.seat === H() ? "me" : "", p.to_act ? "to-act" : "",
      p.folded ? "folded" : "", p.busted ? "busted" : "",
      p.winner && S.status !== "running" && S.status !== "your_turn" ? "winner" : ""].join(" ");
    const hole = p.cards ? p.cards.map((c) => cardHTML(c)).join("") : "";
    const tagCls = (p.last_action || "").toLowerCase().split(" ")[0];
    const tag = p.busted ? `<span class="tag fold">Out</span>`
      : p.last_action ? `<span class="tag ${p.all_in ? "all-in" : tagCls}">${esc(p.last_action)}</span>` : "";
    const blind = p.is_sb ? "SB" : p.is_bb ? "BB" : "";
    return `<div class="${cls}" style="left:${pos.left}%;top:${pos.top}%">
      <div class="hole">${hole}</div>
      <div class="plate">${tag}
        <div class="name">${esc(p.name)}${blind ? `<span class="blind-tag">${blind}</span>` : ""}</div>
        <div class="stack">${p.busted ? "—" : fmt(p.stack)}${p.all_in && !p.folded ? " · all-in" : ""}</div>
      </div></div>`;
  }).join("");
  setHTML("seats", seats);

  const bets = S.players.map((p) => {
    let out = "";
    if (p.bet > 0) {
      const pos = seatPos(slot(p.seat), n, 29, 23);
      out += `<div class="bet" style="left:${pos.left}%;top:${pos.top}%"><span class="chip"></span>${fmt(p.bet)}</div>`;
    }
    if (p.is_button) {
      const pos = seatPos(slot(p.seat), n, 33, 28, n > 2 ? 14 : 22);
      out += `<div class="dealer" style="left:${pos.left}%;top:${pos.top}%">D</div>`;
    }
    return out;
  }).join("");
  setHTML("bets", bets);

  // board: animate only newly dealt cards
  const prev = memo.boardCards || [];
  const board = S.board.map((c, i) => cardHTML(c, prev[i] === c ? "" : "deal")).join("")
    + Array.from({ length: 5 - S.board.length }, () => `<div class="slot"></div>`).join("");
  memo.boardCards = S.board.slice();
  setHTML("board", board);

  const live = S.status === "running" || S.status === "your_turn";
  setHTML("pot", S.pot ? `Pot ${fmt(S.pot)}` : "");
  setHTML("banner", S.result && !live ? bannerText(S.result) : "");
}

function bannerText(r) {
  const ranks = {};
  for (const e of r.showdown) if (e.hand_rank) ranks[e.seat] = e.hand_rank;
  return r.pots.map((pot, i) => {
    const label = r.pots.length > 1 ? (i === 0 ? "Main pot" : `Side pot ${i}`) + ": " : "";
    const ws = pot.winners;
    const who = ws.map(nameOf).join(" & ");
    const verb = ws.length === 1 && ws[0] === H() ? "win" : "wins";
    const what = ws.length > 1 ? ` split ${fmt(pot.amount)}` : ` ${verb} ${fmt(pot.amount)}`;
    const how = ranks[ws[0]] ? ` with ${ranks[ws[0]]}` : "";
    return esc(`${label}${who}${what}${how}`);
  }).join("<br>");
}

function renderActionBar() {
  const st = S.status;
  const req = S.request;
  const toAct = S.players.find((p) => p.to_act);
  const me = H() !== null ? S.players[H()] : null;
  const key = [st, req ? `${req.hand_number}|${req.street}|${req.action_history.length}` : "",
    S.auto_next, !!S.finished, toAct ? toAct.seat : "-", me ? me.busted : "", S.paused].join("|");
  if (memo.barKey === key) return;
  memo.barKey = key;

  const pauseBtn = `<button class="btn act" onclick="togglePause()">${S.paused ? "Resume" : "Pause"} <kbd>P</kbd></button>`;
  const again = `<button class="btn primary" onclick="restart()">Rematch</button>
    <a class="btn" href="/#${isWatch() ? "watch" : "play"}">Change setup</a>`;
  let html;
  if (st === "your_turn" && req) {
    html = actionControls(req);
  } else if (st === "match_over") {
    const ranks = S.finished && S.finished.rankings;
    const text = !ranks ? "Match over."
      : me ? `Match over — you finished #${ranks.indexOf(H()) + 1} of ${S.players.length}.`
        : `Match over — ${esc(S.players[ranks[0]].name)} wins after ${S.finished.hands_played} hands.`;
    html = `<div class="status">${text}</div>${again}`;
  } else if (me && me.busted) {
    html = `<div class="status">You're out of chips — the bots are finishing the match.</div>${again}`;
  } else if (st === "hand_over" && !S.auto_next) {
    html = `${isWatch() ? pauseBtn : ""}<div class="status">Hand over.</div>
      <button class="btn primary act" onclick="nextHand()">Next hand <kbd>Space</kbd></button>`;
  } else {
    const msg = S.paused ? "Paused." : st === "hand_over" ? "Next hand dealing…"
      : toAct ? `${isWatch() ? "" : "Waiting for "}${esc(toAct.name)}${isWatch() ? " to act…" : "…"}` : "Dealing…";
    html = `${isWatch() ? pauseBtn : ""}<div class="status">${msg}</div>`;
  }
  $("actionBar").innerHTML = html;
  if (st === "your_turn" && req) wireRaise(req);
}

function actionControls(req) {
  const canCheck = req.legal_actions.includes("check");
  const canRaise = req.legal_actions.includes("raise");
  const callAmt = req.to_call;
  const callAllIn = !canCheck && callAmt >= req.your_stack;
  const isBet = canCheck && S.street !== "preflop";
  let raise = "";
  if (canRaise) {
    const presets = [["Min", "min"], ["⅓", 1 / 3], ["½", 0.5], ["¾", 0.75], ["Pot", 1], ["All-in", "max"]];
    raise = `<div class="raise-box">
      <div class="raise-row">
        <input type="range" id="raiseSlider" min="${req.min_raise_to}" max="${req.max_raise_to}" step="1" value="${req.min_raise_to}" aria-label="Raise amount">
        <input type="number" id="raiseInput" min="${req.min_raise_to}" max="${req.max_raise_to}" value="${req.min_raise_to}" aria-label="Raise to">
      </div>
      <div class="presets">${presets.map(([l, v]) => `<button class="btn" data-preset="${v}">${l}</button>`).join("")}</div>
    </div>
    <button class="btn primary act" id="raiseBtn" data-bet="${isBet ? 1 : 0}">${isBet ? "Bet" : "Raise to"} ${fmt(req.min_raise_to)}</button>`;
  }
  return `
    ${canCheck ? `<button class="btn act fold" disabled title="Nothing to call">Fold</button>`
      : `<button class="btn act fold" onclick="act('fold')">Fold <kbd>F</kbd></button>`}
    <button class="btn act call" onclick="act('${canCheck ? "check" : "call"}')">
      ${canCheck ? "Check" : callAllIn ? `All-in ${fmt(callAmt)}` : `Call ${fmt(callAmt)}`} <kbd>C</kbd></button>
    ${raise || `<div class="status">${canCheck ? "" : "No raise available"}</div>`}`;
}

function presetAmount(req, v) {
  if (v === "min") return req.min_raise_to;
  if (v === "max") return req.max_raise_to;
  const potAfterCall = req.pot + req.to_call;
  const target = req.your_bet + req.to_call + Math.floor(Number(v) * potAfterCall);
  return Math.max(req.min_raise_to, Math.min(req.max_raise_to, target));
}

function wireRaise(req) {
  const slider = $("raiseSlider"), input = $("raiseInput"), btn = $("raiseBtn");
  if (!slider) return;
  const set = (v) => {
    v = Math.max(req.min_raise_to, Math.min(req.max_raise_to, Math.round(Number(v) || 0)));
    slider.value = v; input.value = v;
    btn.textContent = v === req.max_raise_to ? `All-in ${fmt(v)}`
      : `${btn.dataset.bet === "1" ? "Bet" : "Raise to"} ${fmt(v)}`;
    return v;
  };
  slider.oninput = () => set(slider.value);
  input.onchange = () => set(input.value);
  input.onkeydown = (e) => { if (e.key === "Enter") { e.preventDefault(); btn.click(); } };
  document.querySelectorAll("[data-preset]").forEach((b) => {
    b.onclick = () => set(presetAmount(req, b.dataset.preset));
  });
  btn.onclick = () => act("raise", set(input.value));
}

function signed(n, digits = 0) {
  const v = digits ? Number(n).toFixed(digits) : fmt(n);
  return (n > 0 ? "+" : "") + v;
}
const tone = (n) => (n > 0 ? "pos" : n < 0 ? "neg" : "");

function renderSide() {
  const s = S.session;
  if (isWatch()) {
    const rows = S.players.slice().sort((a, b) => b.stack - a.stack)
      .map((p, i) => `<tr class="${p.busted ? "out" : ""}"><td class="rank">${i + 1}</td><td>${esc(p.name)}</td>
        <td class="num">${p.busted ? "out" : fmt(p.stack)}</td>
        <td class="num ${tone(p.net)}">${signed(p.net)}</td></tr>`).join("");
    setHTML("session", `<h2 class="first">Leaderboard</h2>
      <table class="leader"><thead><tr><th></th><th>Bot</th><th>Stack</th><th>Net</th></tr></thead><tbody>${rows}</tbody></table>
      <div class="mini-stats"><span>${s.hands} hands</span><span>Biggest pot ${fmt(s.biggest_pot)}</span></div>`);
    setHTML("keys", `Keys: <kbd>P</kbd> pause · <kbd>Space</kbd> next hand`);
  } else {
    setHTML("session", `<div class="session">
      <div class="stat"><div class="k">Session</div><div class="v ${tone(s.net)}">${signed(s.net)}</div></div>
      <div class="stat"><div class="k">In big blinds</div><div class="v ${tone(s.net)}">${signed(s.net / s.bb, 1)}</div></div>
      <div class="stat"><div class="k">Hands played</div><div class="v">${s.hands}</div></div>
      <div class="stat"><div class="k">Biggest pot</div><div class="v">${fmt(s.biggest_pot)}</div></div></div>`);
    setHTML("keys", `Keys: <kbd>F</kbd> fold · <kbd>C</kbd> check/call · <kbd>R</kbd> raise · <kbd>Space</kbd> next hand`);
  }
  const changed = setHTML("log", S.log.map((l) => `<li class="${l.kind}">${esc(l.text)}</li>`).join(""));
  if (changed) $("log").scrollTop = $("log").scrollHeight;
}

// ---------------- actions ----------------

async function act(action, amount) {
  if (!S || S.status !== "your_turn") return;
  memo.barKey = null;
  $("actionBar").innerHTML = `<div class="status">…</div>`;
  await api("/api/action", amount === undefined ? { action } : { action, amount });
  poll();
}

async function nextHand() { await api("/api/next", {}); poll(); }
async function togglePause() { await api("/api/settings", { paused: !S.paused }); poll(); }

async function restart() {
  if (!S || !S.last_new) { location.href = "/"; return; }
  const r = await api("/api/new", S.last_new);
  if (r.error) { memo.barKey = null; $("actionBar").innerHTML = `<div class="status err">${esc(r.error)}</div>`; return; }
  Object.keys(memo).forEach((k) => delete memo[k]);
  poll();
}
Object.assign(window, { act, nextHand, togglePause, restart });

document.addEventListener("keydown", (e) => {
  if (!S || ["INPUT", "SELECT", "TEXTAREA"].includes(e.target.tagName)) return;
  const k = e.key.toLowerCase();
  if (S.status === "your_turn" && S.request) {
    const legal = S.request.legal_actions;
    if (k === "f" && legal.includes("fold")) act("fold");
    else if (k === "c") act(legal.includes("check") ? "check" : "call");
    else if (k === "r" && $("raiseInput")) { e.preventDefault(); $("raiseInput").focus(); $("raiseInput").select(); }
  } else if ((k === " " || k === "n") && S.status === "hand_over") {
    e.preventDefault();
    nextHand();
  } else if (k === "p" && isWatch()) {
    togglePause();
  }
});

$("reveal").onchange = (e) => api("/api/settings", { reveal: e.target.checked });
$("autonext").onchange = (e) => api("/api/settings", { auto_next: e.target.checked });
$("speed").onchange = (e) => api("/api/settings", { speed: Number(e.target.value) });
$("restartBtn").onclick = restart;

// ---------------- polling ----------------

let pollTimer = null;
async function poll() {
  clearTimeout(pollTimer);
  try {
    const st = await api("/api/state");
    if (st.rev !== lastRev || st.status === "no_game") {
      lastRev = st.rev;
      S = st;
      render();
    }
  } catch {
    memo.barKey = null;
    $("actionBar").innerHTML = `<div class="status err">Can't reach the server — is play.py still running?</div>`;
  }
  pollTimer = setTimeout(poll, 180);
}
poll();
