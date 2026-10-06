"use strict";

const MODES = {
  play: {
    lineupTitle: "Opponents", hint: "You sit in seat 0.", min: 1, max: 9, seatOffset: 1,
    go: "Deal me in", dflt: ["random", "random", "random", "random", "random"],
  },
  watch: {
    lineupTitle: "Bots at the table", hint: "Every seat is a bot. Cards are face up.", min: 2, max: 10,
    seatOffset: 0, go: "Start watching", dflt: ["random", "caller", "raiser", "random", "random", "folder"],
  },
  simulate: {
    lineupTitle: "Lineup", hint: "Seats are shuffled every match. Bots that share a name are pooled in the stats.",
    min: 2, max: 10, seatOffset: 0, go: "Run simulation", dflt: ["random", "caller", "raiser", "random", "random", "folder"],
  },
};
const FIELDS = ["stack", "sb", "bb", "ante", "hands", "blind_up", "matches", "seed", "workers", "speed"];

let mode = null;
let editor = null;
let info = null;

function select(m) {
  if (editor && mode) saveDraft();
  mode = m;
  document.querySelectorAll(".mode").forEach((b) => b.setAttribute("aria-selected", b.dataset.mode === m));
  const cfg = MODES[m];
  $("config").hidden = false;
  $("config").dataset.mode = m;
  $("lineupTitle").textContent = cfg.lineupTitle;
  $("lineupHint").textContent = cfg.hint;
  $("go").textContent = cfg.go;
  $("formError").textContent = "";
  const draft = store.get("draft." + m, {});
  const initial = draft.bots || (m === "play" && info?.default_bots) || cfg.dflt;
  editor = new LineupEditor($("lineup"), { min: cfg.min, max: cfg.max, initial, seatOffset: cfg.seatOffset });
  const f = $("form").elements;
  for (const k of FIELDS) if (draft[k] !== undefined && f[k]) f[k].value = draft[k];
  for (const k of ["csv_detail", "log"]) if (draft[k] !== undefined) f[k].checked = draft[k];
  if (!draft.workers && info) f.workers.value = info.sim_defaults.workers;
  history.replaceState(null, "", "#" + m);
}

function formValues() {
  const f = $("form").elements;
  const v = { bots: editor.value() };
  for (const k of FIELDS) if (f[k] && f[k].value !== "") v[k] = Number(f[k].value);
  v.csv_detail = f.csv_detail.checked;
  v.log = f.log.checked;
  return v;
}

function saveDraft() { store.set("draft." + mode, formValues()); }

$("form").onsubmit = async (e) => {
  e.preventDefault();
  const v = formValues();
  saveDraft();
  if (v.bb < v.sb) { $("formError").textContent = "Big blind must be at least the small blind."; return; }
  $("go").disabled = true;
  try {
    const r = mode === "simulate"
      ? await api("/api/sim/start", v)
      : await api("/api/new", { ...v, mode, speed: mode === "watch" ? v.speed : 0.7 });
    if (r.error) { $("formError").textContent = r.error; return; }
    location.href = mode === "simulate" ? "/sim" : "/table";
  } catch {
    $("formError").textContent = "Can't reach the server — is play.py running?";
  } finally {
    $("go").disabled = false;
  }
};

document.querySelectorAll(".mode").forEach((b) => b.onclick = () => select(b.dataset.mode));

async function init() {
  try { info = await api("/api/info"); } catch { info = null; }
  const parts = [];
  if (info?.game && !info.game.finished) {
    const what = info.game.mode === "play" ? "Your game" : "A bot match";
    parts.push(`<a class="resume" href="/table"><b>${what} is in progress</b> · ${info.game.hands} hands played <span>Resume →</span></a>`);
  }
  if (info?.sim_running) {
    parts.push(`<a class="resume" href="/sim"><b>A simulation is running</b> <span>View progress →</span></a>`);
  }
  $("resume").innerHTML = parts.join("");
  const fromHash = location.hash.slice(1);
  select(MODES[fromHash] ? fromHash : store.get("lastMode", "play"));
}
window.addEventListener("beforeunload", () => { if (mode) { saveDraft(); store.set("lastMode", mode); } });
init();
