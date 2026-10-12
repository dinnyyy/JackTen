"""Batch simulation: run many matches in parallel and aggregate statistics.

Shared by the CLI (simulate.py) and the web UI (Simulate page).

Each bot is `spec` or `label=spec`; bots sharing a label are pooled in the stats.
Seats are shuffled every match so no bot keeps a positional edge.

Output, in <out>/<run id>/:
    summary.json                 everything the Simulate page shows
    bot_summary.csv              per-bot aggregate stats
    cumulative_winnings.csv      running net bb per bot, hand by hand (downsampled)
    matches.csv                  one row per seat per match
    hands.csv / actions.csv / pots.csv   per-hand, per-decision, per-pot detail (csv_detail=True)
    errors.csv                   bot timeouts / crashes
    histories/match_XXXX.ndjson  full hand histories (log=True)
See docs/sim_outputs.md for every column.
"""

import json
import math
import os
import random
import time
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime

from engine.bots import make_bot, parse_spec
from engine.export import CsvExporter, TABLES, combine_parts, write_rows
from engine.history import HistoryLogger
from engine.match import Match, MatchConfig, BlindLevel
from engine.stats import StatsTracker, merge, summarise

DEFAULTS = {
    "bots": ["random"] * 6,
    "matches": 100,
    "hands": 500,
    "stack": 20000,
    "sb": 50,
    "bb": 100,
    "ante": 0,
    "blind_up": 0,
    "seed": None,
    "workers": max(1, (os.cpu_count() or 2) - 1),
    "time_ms": 5000,
    "bank_ms": 30000,
    "out": os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "sims"),
    "log": True,
    "csv_detail": True,
}
EXTRA_FILES = {
    "bot_summary": "Per-bot aggregate stats: bb/100 with 95% CI, placement, VPIP, PFR, AF, WTSD, ...",
    "cumulative_winnings": "Running net big blinds per bot across every hand of the run (downsampled)",
}
SERIES_POINTS = 400


def parse_lineup(specs: list[str]) -> list[tuple[str, str]]:
    out = []
    for i, raw in enumerate(specs):
        label, spec = parse_spec(raw)
        if label is None:
            label = spec if not spec.startswith(("cmd:", "py:")) else f"ext{i}"
        out.append((label, spec))
    return out


def blind_schedule(sb, bb, ante, every, hands) -> list[BlindLevel]:
    if not every:
        return [BlindLevel(0, sb, bb, ante)]
    levels, k = [], 0
    while k * every < hands:
        m = 2 ** k
        levels.append(BlindLevel(k * every, sb * m, bb * m, ante * m))
        k += 1
    return levels


def run_one(job: dict) -> dict:
    """Play one match. Top-level so worker processes can import it."""
    rng = random.Random(job["seed"])
    lineup = list(job["lineup"])
    rng.shuffle(lineup)
    labels = [l for l, _ in lineup]
    bots = [make_bot(spec, random.Random(rng.random())) for _, spec in lineup]
    cfg = MatchConfig(num_hands=job["hands"], starting_stack=job["stack"],
                      blind_schedule=job["schedule"], seed=job["seed"],
                      time_per_action_ms=job["time_ms"], time_bank_ms=job["bank_ms"])
    tracker = StatsTracker(labels)
    tables = ("actions", "hands", "pots", "matches", "errors") if job["csv_detail"] else ("matches", "errors")
    observers = [tracker, CsvExporter(job["parts_dir"], job["index"], job["seed"], labels, tables)]
    if job["log_path"]:
        observers.append(HistoryLogger(job["log_path"], {"seat_labels": labels}))
    end = Match(bots, cfg, names=labels, observers=observers).run()
    return {
        "index": job["index"],
        "stats": tracker.stats,
        "series_labels": list(tracker.stats),
        "series": tracker.series,
        "hands": end["hands_played"],
    }


def cumulative_series(results: list[dict], labels: list[str]) -> dict:
    """Cumulative net bb per label across all hands (matches in index order), downsampled."""
    total = {l: 0.0 for l in labels}
    xs, lines = [], {l: [] for l in labels}
    n_hands = sum(len(r["series"]) for r in results)
    step = max(1, math.ceil(n_hands / SERIES_POINTS))
    i = 0
    xs.append(0)
    for l in labels:
        lines[l].append(0.0)
    for r in sorted(results, key=lambda r: r["index"]):
        cols = r["series_labels"]
        for row in r["series"]:
            for l, v in zip(cols, row):
                total[l] += v
            i += 1
            if i % step == 0 or i == n_hands:
                xs.append(i)
                for l in labels:
                    lines[l].append(round(total[l], 1))
    return {"x": xs, "lines": lines}


LIVE_MIN_S = 2.0   # minimum gap between live snapshots; also kept >= 5x the last snapshot's cost


def run_simulation(params: dict, on_progress=None, cancel=None, on_snapshot=None) -> dict:
    """on_snapshot(partial_summary) is called every few seconds with the stats and chart series so far."""
    p = {**DEFAULTS, **{k: v for k, v in params.items() if v is not None}}
    lineup = parse_lineup(p["bots"])
    if not 2 <= len(lineup) <= 10:
        raise ValueError("need 2-10 bots")
    for _, spec in lineup:  # fail fast on typos (external bots are checked when launched)
        if not spec.startswith(("cmd:", "py:")):
            make_bot(spec)
    labels = list(dict.fromkeys(l for l, _ in lineup))

    run_id = base_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    k = 1
    while os.path.exists(os.path.join(p["out"], run_id)):
        k += 1
        run_id = f"{base_id}-{k}"
    run_dir = os.path.join(p["out"], run_id)
    hist_dir = os.path.join(run_dir, "histories")
    parts_dir = os.path.join(run_dir, "parts")
    os.makedirs(parts_dir, exist_ok=True)
    if p["log"]:
        os.makedirs(hist_dir, exist_ok=True)
    seed = p["seed"] if p["seed"] is not None else random.randrange(2 ** 31)
    schedule = blind_schedule(p["sb"], p["bb"], p["ante"], p["blind_up"], p["hands"])
    jobs = [{
        "index": i, "seed": seed + i, "lineup": lineup, "hands": p["hands"], "stack": p["stack"],
        "schedule": schedule, "time_ms": p["time_ms"], "bank_ms": p["bank_ms"],
        "log_path": os.path.join(hist_dir, f"match_{i:04d}.ndjson") if p["log"] else None,
        "parts_dir": parts_dir, "csv_detail": p["csv_detail"],
    } for i in range(p["matches"])]

    t0 = time.time()
    stats, results = {}, []
    hands = 0
    cancelled = False
    next_snap = t0 + LIVE_MIN_S
    pool = ProcessPoolExecutor(max_workers=p["workers"])
    try:
        pending = {pool.submit(run_one, j) for j in jobs}
        while pending:
            if cancel is not None and cancel.is_set():
                cancelled = True
                break
            done, pending = wait(pending, timeout=0.25, return_when=FIRST_COMPLETED)
            for fut in done:
                res = fut.result()
                merge(stats, res["stats"])
                results.append(res)
                hands += res["hands"]
            if done and on_progress:
                on_progress(len(results), len(jobs), hands, time.time() - t0)
            if done and on_snapshot and time.time() >= next_snap:
                t1 = time.time()
                on_snapshot({"matches_played": len(results), "total_hands": hands,
                             "elapsed_s": round(t1 - t0, 2), "bots": summarise(stats),
                             "series": cumulative_series(results, labels)})
                next_snap = time.time() + max(LIVE_MIN_S, 5 * (time.time() - t1))
    finally:
        # wait even when cancelling: running matches finish (≤ one match each) and
        # their worker processes exit, which closes their CSV part files
        pool.shutdown(wait=True, cancel_futures=True)

    summary = {
        "id": run_id,
        "created": datetime.now().isoformat(timespec="seconds"),
        "status": "cancelled" if cancelled else "done",
        "params": {**p, "bots": list(p["bots"]), "seed": seed},
        "matches_played": len(results),
        "total_hands": hands,
        "elapsed_s": round(time.time() - t0, 2),
        "bots": summarise(stats) if stats else [],
        "series": cumulative_series(results, labels),
        "dir": run_dir,
    }
    summary["files"] = write_csvs(summary, parts_dir, run_dir)
    with open(os.path.join(run_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=1)
    return summary


def write_csvs(summary: dict, parts_dir: str, run_dir: str) -> list[dict]:
    counts = {"bot_summary": write_rows(os.path.join(run_dir, "bot_summary.csv"), summary["bots"])}
    ser = summary["series"]
    counts["cumulative_winnings"] = write_rows(
        os.path.join(run_dir, "cumulative_winnings.csv"),
        [{"hand_index": x, **{f"{l}_bb": ser["lines"][l][i] for l in ser["lines"]}}
         for i, x in enumerate(ser["x"])])
    counts.update(combine_parts(parts_dir, run_dir))
    files = []
    for name in ["bot_summary", "matches", "hands", "actions", "pots", "cumulative_winnings", "errors"]:
        path = os.path.join(run_dir, f"{name}.csv")
        if not os.path.isfile(path):
            continue
        desc = EXTRA_FILES.get(name) or TABLES[name][0]
        files.append({"name": f"{name}.csv", "rows": counts.get(name, 0),
                      "bytes": os.path.getsize(path), "description": desc})
    return files


def list_runs(out: str = DEFAULTS["out"]) -> list[dict]:
    """Past runs, newest first (lightweight metadata only)."""
    runs = []
    if not os.path.isdir(out):
        return runs
    for name in sorted(os.listdir(out), reverse=True):
        path = os.path.join(out, name, "summary.json")
        if not os.path.isfile(path):
            continue
        try:
            with open(path) as f:
                s = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        runs.append({"id": s.get("id", name), "created": s.get("created"), "status": s.get("status", "done"),
                     "bots": s.get("params", {}).get("bots", []), "matches": s.get("matches_played"),
                     "hands": s.get("total_hands")})
    return runs


def load_run(run_id: str, out: str = DEFAULTS["out"]) -> dict | None:
    if not run_id.replace("-", "").isdigit():
        return None
    path = os.path.join(out, run_id, "summary.json")
    if not os.path.isfile(path):
        return None
    with open(path) as f:
        return json.load(f)
