"use strict";
// Shared helpers for every page.

const $ = (id) => document.getElementById(id);
const BUILTINS = ["random", "caller", "raiser", "folder"];
const BOT_HELP = {
  random: "uniformly random legal moves",
  caller: "always checks or calls",
  raiser: "raises pot whenever it can",
  folder: "checks if free, otherwise folds",
};
const fmt = (n) => Number(n).toLocaleString("en-US");

function esc(s) {
  return String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

async function api(path, body) {
  const r = await fetch(path, body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  return r.json();
}

const store = {
  get(k, dflt = null) { try { const v = localStorage.getItem("jackten." + k); return v ? JSON.parse(v) : dflt; } catch { return dflt; } },
  set(k, v) { try { localStorage.setItem("jackten." + k, JSON.stringify(v)); } catch {} },
};

/** Editable list of bot specs: built-in dropdown, or a custom `Name=cmd:...` line. */
class LineupEditor {
  constructor(el, { min, max, initial, seatOffset = 0, onChange = () => {} }) {
    Object.assign(this, { el, min, max, seatOffset, onChange });
    this.bots = initial.slice(0, max);
    while (this.bots.length < min) this.bots.push("random");
    this.render();
  }

  render() {
    const rows = this.bots.map((spec, i) => {
      const builtin = BUILTINS.includes(spec);
      return `<div class="opp-row">
        <span class="seatno">Seat ${i + this.seatOffset}</span>
        <select data-i="${i}" aria-label="Bot for seat ${i + this.seatOffset}">
          ${BUILTINS.map((b) => `<option value="${b}" ${b === spec ? "selected" : ""}>${b}</option>`).join("")}
          <option value="custom" ${builtin ? "" : "selected"}>custom…</option>
        </select>
        ${builtin ? `<span class="bot-help">${BOT_HELP[spec]}</span>`
          : `<input data-i="${i}" value="${esc(spec)}" placeholder="MyBot=cmd:python my_bot.py" spellcheck="false">`}
        <button type="button" class="icon-btn" data-del="${i}" title="Remove" ${this.bots.length <= this.min ? "disabled" : ""}>×</button>
      </div>`;
    }).join("");
    this.el.innerHTML = `<div class="opp-list">${rows}</div>
      <button type="button" class="btn small ghost add-bot" ${this.bots.length >= this.max ? "disabled" : ""}>+ Add bot</button>`;
    this.el.querySelectorAll("select").forEach((sel) => sel.onchange = () => {
      this.bots[sel.dataset.i] = sel.value === "custom" ? "MyBot=cmd:python bots/random_bot.py" : sel.value;
      this.render(); this.onChange();
    });
    this.el.querySelectorAll("input").forEach((inp) => inp.oninput = () => {
      this.bots[inp.dataset.i] = inp.value; this.onChange();
    });
    this.el.querySelectorAll("[data-del]").forEach((b) => b.onclick = () => {
      this.bots.splice(Number(b.dataset.del), 1); this.render(); this.onChange();
    });
    this.el.querySelector(".add-bot").onclick = () => {
      this.bots.push("random"); this.render(); this.onChange();
    };
  }

  value() { return this.bots.map((b) => b.trim()).filter(Boolean); }
}
