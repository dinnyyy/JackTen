"use strict";
// Simulations page: live progress, past runs, charts, stats table, CSV downloads.

// Categorical palette (dark steps), fixed order; validated against the page surface.
const SERIES = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"];
const OTHER = "#7d817a";

const COLS = [
  ["bot", "Bot", "Label from the lineup; bots sharing a label are pooled"],
  ["hands", "Hands", "Hands dealt to this bot"],
  ["net_chips", "Net chips", "Total chips won or lost"],
  ["bb_per_100", "bb/100", "Big blinds won per 100 hands (each hand normalised by its own big blind)"],
  ["bb_per_100_ci95", "±95%", "Half-width of the 95% confidence interval on bb/100"],
  ["avg_place", "Avg place", "Average finishing position (1 = won the match)"],
  ["win_rate", "Win %", "Share of matches finished in 1st"],
  ["bust_rate", "Bust %", "Share of matches that ended with zero chips"],
  ["avg_final_stack", "Avg stack", "Average chips at the end of a match"],
  ["vpip", "VPIP", "% of hands voluntarily putting chips in preflop"],
  ["pfr", "PFR", "% of hands raising preflop"],
  ["threebet", "3-bet", "% re-raising when facing exactly one preflop raise"],
  ["af", "AF", "Postflop aggression factor: (bets + raises) / calls"],
  ["wtsd", "WTSD", "% of flops seen that went to showdown"],
  ["wsd", "W$SD", "% of showdowns that won chips"],
  ["bot_errors", "Errors", "Timeouts, crashes and invalid responses"],
];

let current = null;        // summary being shown
let colorOf = {};
let statusTimer = null;
let lastLive = null;      // matches_played of the live snapshot last drawn

// ---------------- data ----------------

async function loadRuns(activeId) {
  const runs = await api("/api/sim/runs");
  $("runs").innerHTML = runs.length ? runs.map((r) => `
    <li><a href="#run=${r.id}" class="${r.id === activeId ? "active" : ""}">
      <span class="run-id">${esc(r.id)}${r.status === "cancelled" ? ' <em>cancelled</em>' : ""}</span>
      <span class="run-meta">${esc(r.bots.join(", "))}</span>
      <span class="run-meta">${fmt(r.matches ?? 0)} matches · ${fmt(r.hands ?? 0)} hands</span>
    </a></li>`).join("") : `<li class="empty">No runs yet.</li>`;
  return runs;
}

async function showRun(id) {
  const s = await api("/api/sim/run/" + encodeURIComponent(id));
  if (s.error) { $("result").innerHTML = `<div class="empty-state">Run not found.</div>`; return; }
  lastLive = null;
  renderResult(s);
  loadRuns(id);
}

async function pollStatus() {
  clearTimeout(statusTimer);
  let st;
  try { st = await api("/api/sim/status"); } catch { return; }
  if (st.running) {
    renderProgress(st);
    if (st.live && st.live.n !== lastLive && !/run=/.test(location.hash)) {
      lastLive = st.live.n;
      renderResult(st.live);
    }
    statusTimer = setTimeout(pollStatus, 500);
    return;
  }
  $("progress").innerHTML = st.error ? `<div class="box err">Simulation failed: ${esc(st.error)}</div>` : "";
  if (st.result && (!current || current.id !== st.result.id) && pollStatus.watching) {
    pollStatus.watching = false;
    location.hash = "run=" + st.result.id;
  }
}

function renderProgress(st) {
  pollStatus.watching = true;
  const p = st.progress;
  const pct = p.total ? (100 * p.done) / p.total : 0;
  const rate = p.elapsed > 0 ? p.done / p.elapsed : 0;
  const eta = rate > 0 ? Math.max(0, (p.total - p.done) / rate) : null;
  $("progress").innerHTML = `<div class="box progress-card">
    <div class="progress-head">
      <h1>${st.cancelling ? "Cancelling…" : p.done >= p.total ? "Writing CSV files…" : "Simulating…"}</h1>
      <button class="btn" onclick="cancelSim()" ${st.cancelling ? "disabled" : ""}>Cancel</button>
    </div>
    <div class="lineup">${(st.params.bots || []).map((b) => `<span class="chip-tag">${esc(b)}</span>`).join("")}</div>
    <div class="bar" role="progressbar" aria-valuenow="${Math.round(pct)}" aria-valuemin="0" aria-valuemax="100"><div style="width:${pct}%"></div></div>
    <div class="progress-meta"><span><b>${fmt(p.done)}</b> / ${fmt(p.total)} matches</span>
      <span><b>${fmt(p.hands)}</b> hands</span><span>${st.elapsed.toFixed(1)}s</span>
      ${eta !== null ? `<span>~${Math.ceil(eta)}s left</span>` : ""}</div>
  </div>`;
}

async function cancelSim() { await api("/api/sim/cancel", {}); pollStatus(); }
window.cancelSim = cancelSim;

// ---------------- result ----------------

function renderResult(s) {
  current = s;
  const labels = Object.keys(s.series.lines);
  colorOf = Object.fromEntries(labels.map((l, i) => [l, SERIES[i] ?? OTHER]));
  const p = s.params;
  const blinds = `${fmt(p.sb)}/${fmt(p.bb)}${p.ante ? ` ante ${fmt(p.ante)}` : ""}${p.blind_up ? `, doubling every ${p.blind_up}` : ""}`;
  const hps = s.elapsed_s > 0 ? Math.round(s.total_hands / s.elapsed_s) : 0;
  const best = s.bots[0];

  $("result").innerHTML = `
    <header class="run-head">
      <div>
        <h1>Run ${esc(s.id)} ${s.status === "cancelled" ? '<span class="badge warn">cancelled</span>' : s.status === "running" ? '<span class="badge">live</span>' : ""}</h1>
        <p class="hint">${esc(s.created || "")} · seed ${esc(p.seed)} · ${fmt(p.stack)} stacks · blinds ${blinds} · up to ${fmt(p.hands)} hands per match</p>
        <div class="lineup">${p.bots.map((b) => `<span class="chip-tag">${esc(b)}</span>`).join("")}</div>
      </div>
    </header>
    <div class="tiles">
      <div class="tile"><div class="k">Hands</div><div class="v">${fmt(s.total_hands)}</div></div>
      <div class="tile"><div class="k">Matches</div><div class="v">${fmt(s.matches_played)}</div></div>
      <div class="tile"><div class="k">Run time</div><div class="v">${s.elapsed_s}s</div><div class="sub">${fmt(hps)} hands/s</div></div>
      <div class="tile"><div class="k">Top bb/100</div><div class="v">${best ? esc(best.bot) : "—"}</div>
        <div class="sub">${best ? `${signed(best.bb_per_100)} ± ${best.bb_per_100_ci95}` : ""}</div></div>
    </div>
    <section class="box chart-card">
      <h2>Cumulative winnings</h2>
      <p class="hint">Net big blinds per bot, hand by hand across the whole run.</p>
      <div class="legend">${labels.map((l) => `<span><i style="background:${colorOf[l]}"></i>${esc(l)}</span>`).join("")}</div>
      <div class="chart" id="lineChart"></div>
    </section>
    <section class="box chart-card">
      <h2>Win rate</h2>
      <p class="hint">bb/100 with 95% confidence interval. An interval crossing zero means the edge isn't proven yet — run more hands.</p>
      <div class="chart" id="dotChart"></div>
    </section>
    <section class="box">
      <h2>Per-bot stats</h2>
      <div class="table-scroll"><table class="stats">
        <thead><tr>${COLS.map(([k, l, h]) => `<th title="${esc(h)}" class="${k === "bot" ? "" : "num"}">${l}</th>`).join("")}</tr></thead>
        <tbody>${s.bots.map((b) => `<tr>${COLS.map(([k]) => k === "bot"
          ? `<td><i class="sw" style="background:${colorOf[b.bot] ?? OTHER}"></i>${esc(b.bot)}</td>`
          : `<td class="num ${k === "bb_per_100" || k === "net_chips" ? tone(b[k]) : ""}">${cell(k, b[k])}</td>`).join("")}</tr>`).join("")}
        </tbody></table></div>
    </section>`;
  renderDownloads(s);
  drawLine();
  drawDots();
}

function cell(k, v) {
  if (v === null || v === undefined) return "—";
  if (k === "bb_per_100" || k === "net_chips") return signed(v);
  if (["win_rate", "bust_rate", "vpip", "pfr", "threebet", "wtsd", "wsd"].includes(k)) return `${v}%`;
  return typeof v === "number" ? fmt(v) : esc(v);
}
const tone = (n) => (n > 0 ? "pos" : n < 0 ? "neg" : "");
const signed = (n) => (n > 0 ? "+" : "") + fmt(n);

function renderDownloads(s) {
  if (s.status === "running") { $("downloads").innerHTML = ""; return; }
  const files = s.files || [];
  const size = (b) => b > 1e6 ? `${(b / 1e6).toFixed(1)} MB` : b > 1e3 ? `${Math.round(b / 1e3)} KB` : `${b} B`;
  $("downloads").innerHTML = `<h2 class="first">Download</h2>
    <a class="btn primary block" href="/download/${encodeURIComponent(s.id)}.zip">All CSVs (.zip)</a>
    <ul class="files">${files.map((f) => `<li>
      <a href="/download/${encodeURIComponent(s.id)}/${encodeURIComponent(f.name)}" download>${esc(f.name)}</a>
      <span class="file-meta">${fmt(f.rows)} rows · ${size(f.bytes)}</span>
      <span class="file-desc">${esc(f.description)}</span></li>`).join("")}</ul>
    <p class="hint small">Saved in <code>${esc(s.dir)}</code>. Columns are documented in <code>docs/sim_outputs.md</code>.</p>`;
}

// ---------------- charts ----------------

function niceTicks(lo, hi, count = 5) {
  if (lo === hi) { lo -= 1; hi += 1; }
  const raw = (hi - lo) / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw);
  const ticks = [];
  for (let v = Math.floor(lo / step) * step; ; v += step) {  // always cover [lo, hi]
    ticks.push(+v.toFixed(10));
    if (v >= hi) break;
  }
  return ticks;
}
const compact = (v) => Math.abs(v) >= 1e6 ? `${+(v / 1e6).toFixed(1)}M` : Math.abs(v) >= 1e4 ? `${+(v / 1e3).toFixed(1)}k` : fmt(Math.round(v));

function tipShow(html, x, y) {
  const t = $("tip");
  t.innerHTML = html; t.hidden = false;
  const r = t.getBoundingClientRect();
  let left = x + 14, top = y + 14;
  if (left + r.width > innerWidth - 8) left = x - r.width - 14;
  if (top + r.height > innerHeight - 8) top = y - r.height - 14;
  t.style.left = left + "px"; t.style.top = top + "px";
}
const tipHide = () => { $("tip").hidden = true; };

function drawLine() {
  const el = $("lineChart");
  if (!el || !current) return;
  const { x, lines } = current.series;
  const labels = Object.keys(lines);
  const W = el.clientWidth, Hh = 300;
  const direct = labels.length <= 4;
  const m = { l: 56, r: direct ? 96 : 16, t: 10, b: 30 };
  const iw = W - m.l - m.r, ih = Hh - m.t - m.b;
  const all = labels.flatMap((l) => lines[l]);
  const yt = niceTicks(Math.min(0, ...all), Math.max(0, ...all));
  const y0 = yt[0], y1 = yt[yt.length - 1];
  const xMax = x[x.length - 1] || 1;
  const sx = (v) => m.l + (v / xMax) * iw;
  const sy = (v) => m.t + ih - ((v - y0) / (y1 - y0)) * ih;
  const xt = niceTicks(0, xMax, 6).filter((v) => v <= xMax);

  let svg = `<svg width="${W}" height="${Hh}" role="img" aria-label="Cumulative winnings in big blinds per bot">`;
  for (const v of yt) {
    svg += `<line class="${v === 0 ? "zero" : "grid"}" x1="${m.l}" x2="${m.l + iw}" y1="${sy(v)}" y2="${sy(v)}"/>
      <text class="tick" x="${m.l - 8}" y="${sy(v) + 4}" text-anchor="end">${compact(v)}</text>`;
  }
  for (const v of xt) svg += `<text class="tick" x="${sx(v)}" y="${Hh - 8}" text-anchor="middle">${compact(v)}</text>`;
  svg += `<text class="axis-title" x="${m.l + iw}" y="${Hh - 8}" text-anchor="end" dy="-14">hands</text>`;
  for (const l of labels) {
    const d = lines[l].map((v, i) => `${i ? "L" : "M"}${sx(x[i]).toFixed(1)},${sy(v).toFixed(1)}`).join("");
    svg += `<path class="series" d="${d}" stroke="${colorOf[l]}"/>`;
  }
  if (direct) {
    const ends = labels.map((l) => ({ l, y: sy(lines[l][lines[l].length - 1]) })).sort((a, b) => a.y - b.y);
    for (let i = 1; i < ends.length; i++) ends[i].y = Math.max(ends[i].y, ends[i - 1].y + 14);
    for (const e of ends) {
      svg += `<circle cx="${m.l + iw + 8}" cy="${e.y}" r="3.5" fill="${colorOf[e.l]}"/>
        <text class="direct" x="${m.l + iw + 16}" y="${e.y + 4}">${esc(e.l)}</text>`;
    }
  }
  svg += `<g id="hover" visibility="hidden"><line class="crosshair" y1="${m.t}" y2="${m.t + ih}"/>
    ${labels.map((l) => `<circle class="hover-dot" r="4.5" fill="${colorOf[l]}" data-l="${esc(l)}"/>`).join("")}</g>
    <rect class="hit" x="${m.l}" y="${m.t}" width="${iw}" height="${ih}"/></svg>`;
  el.innerHTML = svg;

  const hit = el.querySelector(".hit"), hover = el.querySelector("#hover");
  hit.onmousemove = (ev) => {
    const r = hit.getBoundingClientRect();
    const hx = ((ev.clientX - r.left) / r.width) * xMax;
    let lo = 0, hi = x.length - 1;
    while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (x[mid] < hx) lo = mid; else hi = mid; }
    const i = Math.abs(x[lo] - hx) < Math.abs(x[hi] - hx) ? lo : hi;
    hover.setAttribute("visibility", "visible");
    const line = hover.querySelector("line");
    line.setAttribute("x1", sx(x[i])); line.setAttribute("x2", sx(x[i]));
    hover.querySelectorAll("circle").forEach((c) => {
      c.setAttribute("cx", sx(x[i])); c.setAttribute("cy", sy(lines[c.dataset.l][i]));
    });
    const rows = labels.map((l) => [l, lines[l][i]]).sort((a, b) => b[1] - a[1])
      .map(([l, v]) => `<div class="tip-row"><i style="background:${colorOf[l]}"></i><span>${esc(l)}</span><b>${signed(Math.round(v))} bb</b></div>`).join("");
    tipShow(`<div class="tip-title">Hand ${fmt(x[i])}</div>${rows}`, ev.clientX, ev.clientY);
  };
  hit.onmouseleave = () => { hover.setAttribute("visibility", "hidden"); tipHide(); };
}

function drawDots() {
  const el = $("dotChart");
  if (!el || !current) return;
  const bots = current.bots;
  const W = el.clientWidth, row = 36;
  const m = { l: 120, r: 120, t: 8, b: 28 };
  const Hh = m.t + m.b + row * bots.length;
  const iw = W - m.l - m.r;
  const lo = bots.map((b) => b.bb_per_100 - b.bb_per_100_ci95), hi = bots.map((b) => b.bb_per_100 + b.bb_per_100_ci95);
  const xt = niceTicks(Math.min(0, ...lo), Math.max(0, ...hi), 6);
  const x0 = xt[0], x1 = xt[xt.length - 1];
  const sx = (v) => m.l + ((v - x0) / (x1 - x0)) * iw;

  let svg = `<svg width="${W}" height="${Hh}" role="img" aria-label="bb per 100 hands with 95% confidence intervals">`;
  for (const v of xt) {
    svg += `<line class="${v === 0 ? "zero" : "grid"}" x1="${sx(v)}" x2="${sx(v)}" y1="${m.t}" y2="${Hh - m.b}"/>
      <text class="tick" x="${sx(v)}" y="${Hh - 8}" text-anchor="middle">${compact(v)}</text>`;
  }
  bots.forEach((b, i) => {
    const cy = m.t + row * i + row / 2, c = colorOf[b.bot] ?? OTHER;
    const a = sx(b.bb_per_100 - b.bb_per_100_ci95), z = sx(b.bb_per_100 + b.bb_per_100_ci95);
    svg += `<g class="dot-row" data-i="${i}">
      <rect class="hit" x="0" y="${cy - row / 2}" width="${W}" height="${row}"/>
      <text class="row-label" x="${m.l - 12}" y="${cy + 4}" text-anchor="end">${esc(b.bot)}</text>
      <line class="whisker" x1="${a}" x2="${z}" y1="${cy}" y2="${cy}" stroke="${c}"/>
      <line class="whisker" x1="${a}" x2="${a}" y1="${cy - 5}" y2="${cy + 5}" stroke="${c}"/>
      <line class="whisker" x1="${z}" x2="${z}" y1="${cy - 5}" y2="${cy + 5}" stroke="${c}"/>
      <circle class="dot" cx="${sx(b.bb_per_100)}" cy="${cy}" r="5.5" fill="${c}"/>
      <text class="row-value" x="${m.l + iw + 12}" y="${cy + 4}">${signed(b.bb_per_100)} ± ${fmt(b.bb_per_100_ci95)}</text>
    </g>`;
  });
  el.innerHTML = svg + "</svg>";
  el.querySelectorAll(".dot-row").forEach((g) => {
    const b = bots[g.dataset.i];
    g.onmousemove = (ev) => tipShow(`<div class="tip-title">${esc(b.bot)}</div>
      <div class="tip-row"><span>bb/100</span><b>${signed(b.bb_per_100)}</b></div>
      <div class="tip-row"><span>95% CI</span><b>${fmt(+(b.bb_per_100 - b.bb_per_100_ci95).toFixed(1))} to ${fmt(+(b.bb_per_100 + b.bb_per_100_ci95).toFixed(1))}</b></div>
      <div class="tip-row"><span>Hands</span><b>${fmt(b.hands)}</b></div>`, ev.clientX, ev.clientY);
    g.onmouseleave = tipHide;
  });
}

let resizeT;
addEventListener("resize", () => { clearTimeout(resizeT); resizeT = setTimeout(() => { drawLine(); drawDots(); }, 120); });

// ---------------- routing ----------------

async function route() {
  const m = location.hash.match(/run=([\w-]+)/);
  if (m) return showRun(m[1]);
  const runs = await loadRuns(null);
  if (runs.length) return showRun(runs[0].id);
  const st = await api("/api/sim/status");
  if (st.running) return;
  $("result").innerHTML = `<div class="empty-state"><h1>No simulations yet</h1>
    <p>Pick a lineup and run thousands of hands. Results land here with charts and CSV downloads.</p>
    <a class="btn primary" href="/#simulate">Set one up</a></div>`;
}
addEventListener("hashchange", route);
route();
pollStatus();
