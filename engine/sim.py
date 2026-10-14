"""Batch simulation: run many matches in parallel and aggregate statistics.

Shared by the CLI (simulate.py) and the web UI (Simulate page).

Each bot is `spec` or `label=spec`; bots sharing a label are pooled in the stats.
Seats are shuffled every match so no bot keeps a positional edge.

Evaluation (engine/evaluation.py): confidence intervals come from 100-hand blocks;
`duplicate=True` replays every deal with the bots moved between seats so deal luck
cancels; `bench=True` uses the frozen benchmark seeds. Every bot also gets an
all-in-EV win rate. Comparisons between bots are in summary["evaluation"].

Output, in <out>/<run id>/:
    summary.json                 everything the Simulate page shows
    bot_summary.csv              per-bot aggregate stats
    comparisons.csv              pairwise differences with 95% CIs (Phase 8)
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
import re
import signal
import threading
import random
import time
import multiprocessing
import queue
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime

from engine.bots import make_bot, parse_spec
from engine.evaluation import (BENCH_SEED, evaluate_results, dev_seed, log_bench, overlaps_bench,
                               plays_per_deal, seatings, timestamp)
from engine.export import CsvExporter, TABLES, combine_parts, write_rows
from engine.history import HistoryLogger
from engine.match import Match, MatchConfig, BlindLevel
from engine.stats import BLOCK, StatsTracker, empty, merge, summarise

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
    "duplicate": False,
    "cash": False,
    "bench": False,
}
EXTRA_FILES = {
    "bot_summary": "Per-bot aggregate stats: bb/100 with 95% CI, placement, VPIP, PFR, AF, WTSD, ...",
    "comparisons": "Every pair of bots: bb/100 difference and all-in-EV difference, each with a 95% CI",
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


def run_name(labels: list[str]) -> str:
    """Folder suffix from the bot labels, duplicates collapsed: v2 x3 + v4 x3 -> 'v2-v4'."""
    parts = [re.sub(r"[^A-Za-z0-9.]+", "", l) for l in labels]
    return "-".join(p for p in parts if p)[:60] or "run"


RUN_ID = re.compile(r"\d{8}-\d{6}(_[A-Za-z0-9.-]+)?(-\d+)?")


def blind_schedule(sb, bb, ante, every, hands) -> list[BlindLevel]:
    if not every:
        return [BlindLevel(0, sb, bb, ante)]
    levels, k = [], 0
    while k * every < hands:
        m = 2 ** k
        levels.append(BlindLevel(k * every, sb * m, bb * m, ante * m))
        k += 1
    return levels


_FEED = None   # queue to the parent process, set in each worker by _init_worker


def _init_worker(feed):
    global _FEED
    _FEED = feed
    if hasattr(os, "setpgrp"):
        os.setpgrp()   # own process group, so cancelling can kill this worker and its bot processes together


def _kill_workers(pool):
    """Stop a pool's workers now, along with the external bots they started."""
    for proc in list(getattr(pool, "_processes", {}).values()):
        try:
            if hasattr(os, "killpg"):
                os.killpg(proc.pid, signal.SIGKILL)
            else:
                proc.kill()
        except (ProcessLookupError, PermissionError, OSError):
            try:
                proc.kill()
            except OSError:
                pass


class LiveFeed:
    """Observer that streams each finished hand to the parent so charts update mid-match.

    Must come after the StatsTracker in the observer list: it reads the tracker's
    latest row and running block cells (cumulative, so a lost message costs nothing).
    """

    def __init__(self, tracker: StatsTracker, index: int):
        self.t, self.index = tracker, index

    def on_event(self, m):
        if m["type"] != "hand_result" or _FEED is None:
            return
        t = self.t
        blk = m["hand_number"] // BLOCK
        _FEED.put({"index": self.index, "blk": blk, "block_hands": t.block_hands[blk],
                   "cells": {l: list(t.blocks[l][blk]) for l in t.blocks if blk in t.blocks[l]},
                   "row": dict(zip(t.stats, t.series[-1]))})   # label -> net bb; order differs per match


def run_one(job: dict) -> dict:
    """Play one match. Top-level so worker processes can import it."""
    rng = random.Random(f"{job['seed']}:{job['index']}:bots")
    lineup = list(job["lineup"])          # already in seat order
    labels = [l for l, _ in lineup]
    bots = [make_bot(spec, random.Random(rng.random())) for _, spec in lineup]
    cfg = MatchConfig(num_hands=job["hands"], starting_stack=job["stack"],
                      blind_schedule=job["schedule"], seed=job["seed"],
                      time_per_action_ms=job["time_ms"], time_bank_ms=job["bank_ms"], allin_ev=True,
                      reset_stacks=job["cash"])
    tracker = StatsTracker(labels)
    tables = ("actions", "hands", "pots", "matches", "errors") if job["csv_detail"] else ("matches", "errors")
    observers = [tracker, LiveFeed(tracker, job["index"]), CsvExporter(job["parts_dir"], job["index"], job["seed"], labels, tables)]
    if job["log_path"]:
        observers.append(HistoryLogger(job["log_path"], {"seat_labels": labels}))
    end = Match(bots, cfg, names=labels, observers=observers).run()
    return {
        "index": job["index"],
        "stats": tracker.stats,
        "series_labels": list(tracker.stats),
        "series": tracker.series,
        "blocks": tracker.blocks,
        "block_hands": tracker.block_hands,
        "hands": end["hands_played"],
    }


def with_evaluation(stats: dict, results: list[dict], labels: list[str], plays: int) -> list[dict]:
    """Per-bot rows with block-based CIs and the all-in-EV win rate added."""
    rows = summarise(stats)
    ev = evaluate_results(results, labels, plays)["bots"]
    for r in rows:
        e = ev.get(r["bot"])
        if e and e["blocks"] > 1:
            r["bb_per_100_ci95"] = e["ci95"]       # block-based, replaces the per-hand estimate
        r["bb_per_100_ev"] = round(100 * stats[r["bot"]]["bb_ev_sum"] / max(stats[r["bot"]]["hands"], 1), 2)
        r["ev_ci95"] = e["ci95_ev"] if e else 0.0
        r["sd_100"] = e["sd_100"] if e else 0.0
    return rows


def series_from_rows(rows: list[list[float]], labels: list[str]) -> dict:
    """Cumulative net bb per label from per-hand rows (arrival order), downsampled."""
    step = max(1, math.ceil(len(rows) / SERIES_POINTS))
    total = [0.0] * len(labels)
    xs, lines = [0], {l: [0.0] for l in labels}
    for i, row in enumerate(rows, 1):
        for k, v in enumerate(row):
            total[k] += v
        if i % step == 0 or i == len(rows):
            xs.append(i)
            for k, l in enumerate(labels):
                lines[l].append(round(total[k], 1))
    return {"x": xs, "lines": lines}


def live_bots(stats: dict, live: dict, labels: list[str], plays: int) -> tuple[list[dict], dict]:
    """Per-bot rows for a run in progress: finished matches give the detailed stats
    (VPIP, ...), the streamed blocks give the up-to-the-hand win rates."""
    ev = evaluate_results(list(live.values()), labels, plays)
    rows = summarise({l: stats.get(l) or empty() for l in labels})
    for r in rows:
        e = ev["bots"][r["bot"]]
        r["hands"] = sum(c[2] for res in live.values() for c in res["blocks"].get(r["bot"], {}).values())
        r.update(bb_per_100=e["bb_per_100"], bb_per_100_ci95=e["ci95"], bb_per_100_ev=e["bb_per_100_ev"],
                 ev_ci95=e["ci95_ev"], sd_100=e["sd_100"])
    rows.sort(key=lambda r: -r["bb_per_100"])
    return rows, ev


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


LIVE_MIN_S = 1.0   # minimum gap between live snapshots; also kept >= 5x the last snapshot's cost


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
    if p["bench"]:
        if p["seed"] is not None and p["seed"] != BENCH_SEED:
            raise ValueError(f"--bench uses the frozen seed {BENCH_SEED}; drop --seed")
        p["seed"] = BENCH_SEED
        p["duplicate"] = p["cash"] = True      # the benchmark protocol is fixed
    plays = plays_per_deal(lineup) if p["duplicate"] else 1
    deals = -(-p["matches"] // plays)          # round up so every deal is fully replayed
    if not p["bench"] and p["seed"] is not None and overlaps_bench(p["seed"], deals):
        raise ValueError(f"seeds near {BENCH_SEED} are reserved for --bench")

    run_id = base_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "_" + run_name(labels)
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
    seed = p["seed"] if p["seed"] is not None else dev_seed(deals)
    schedule = blind_schedule(p["sb"], p["bb"], p["ante"], p["blind_up"], p["hands"])
    jobs = []
    for g in range(deals):                     # deal g is played `plays` times, seat order differing
        orders = seatings(lineup, random.Random(f"{seed + g}:seats"))
        if not p["duplicate"]:
            orders = orders[:1]
        for j, order in enumerate(orders):
            i = g * plays + j
            jobs.append({
                "index": i, "seed": seed + g, "lineup": order, "hands": p["hands"], "stack": p["stack"],
                "schedule": schedule, "time_ms": p["time_ms"], "bank_ms": p["bank_ms"],
                "log_path": os.path.join(hist_dir, f"match_{i:04d}.ndjson") if p["log"] else None,
                "parts_dir": parts_dir, "csv_detail": p["csv_detail"], "cash": p["cash"],
            })

    # each external bot is its own process: don't start more matches at once than the CPUs can
    # serve, or no match finishes (and nothing shows up) until all of them do
    external = sum(1 for _, spec in lineup if spec.startswith("cmd:"))
    workers = p["workers"]
    if external and p["workers"] == DEFAULTS["workers"]:
        workers = max(1, (os.cpu_count() or 2) // external)
    t0 = time.time()
    stats, results = {}, []
    hands = 0
    cancelled = False
    next_snap = t0 + LIVE_MIN_S
    feed = multiprocessing.Queue()
    live: dict[int, dict] = {}        # match index -> blocks streamed so far
    rows: list[list[float]] = []      # per-hand net bb, in arrival order
    pool = ProcessPoolExecutor(max_workers=workers, initializer=_init_worker, initargs=(feed,))

    def drain() -> int:
        n = 0
        while True:
            try:
                m = feed.get_nowait()
            except queue.Empty:
                return n
            res = live.setdefault(m["index"], {"index": m["index"], "blocks": {l: {} for l in labels},
                                               "block_hands": {}})
            res["block_hands"][m["blk"]] = m["block_hands"]
            for l, c in m["cells"].items():
                res["blocks"][l][m["blk"]] = c
            rows.append([m["row"][l] for l in labels])
            n += 1

    try:
        pending = {pool.submit(run_one, j) for j in jobs}
        while pending:
            if cancel is not None and cancel.is_set():
                cancelled = True
                break
            done, pending = wait(pending, timeout=0.25, return_when=FIRST_COMPLETED)
            fresh = drain()
            for fut in done:
                res = fut.result()
                merge(stats, res["stats"])
                results.append(res)
                hands += res["hands"]
            if (done or fresh) and on_progress:
                on_progress(len(results), len(jobs), len(rows), time.time() - t0)
            if (done or fresh) and on_snapshot and time.time() >= next_snap:
                t1 = time.time()
                bots, ev = live_bots(stats, live, labels, plays)
                on_snapshot({"matches_played": len(results), "total_hands": len(rows),
                             "elapsed_s": round(t1 - t0, 2), "bots": bots, "evaluation": ev,
                             "series": series_from_rows(rows, labels)})
                next_snap = time.time() + max(LIVE_MIN_S, 5 * (time.time() - t1))
    finally:
        # wait even when cancelling: running matches finish (≤ one match each) and
        # their worker processes exit, which closes their CSV part files
        if cancelled:
            _kill_workers(pool)   # don't wait for running matches to play out
        # keep draining the feed meanwhile: a worker can't exit with unread messages queued
        stop = threading.Event()

        def keep_draining():
            while not stop.is_set():
                drain()
                time.sleep(0.05)
        threading.Thread(target=keep_draining, daemon=True).start()
        pool.shutdown(wait=True, cancel_futures=True)
        stop.set()

    summary = {
        "id": run_id,
        "created": datetime.now().isoformat(timespec="seconds"),
        "status": "cancelled" if cancelled else "done",
        "params": {**p, "bots": list(p["bots"]), "seed": seed},
        "matches_played": len(results),
        "total_hands": hands,
        "elapsed_s": round(time.time() - t0, 2),
        "bots": with_evaluation(stats, results, labels, plays) if stats else [],
        "evaluation": evaluate_results(results, labels, plays) if stats else None,
        "series": cumulative_series(results, labels),
        "dir": run_dir,
    }
    if p["bench"] and not cancelled:
        log_bench(p["out"], {"time": timestamp(), "run": run_id, "bots": list(p["bots"]),
                             "deals": deals, "hands": p["hands"],
                             "pairs": summary["evaluation"]["pairs"]})
    if cancelled:   # killed matches leave partial rows and logs behind: keep completed matches only
        keep = {r["index"] for r in results}
        drop_partial_histories(hist_dir, keep)
    else:
        keep = None
    summary["files"] = write_csvs(summary, parts_dir, run_dir, keep)
    with open(os.path.join(run_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=1)
    return summary


def drop_partial_histories(hist_dir: str, keep: set[int]) -> None:
    if not os.path.isdir(hist_dir):
        return
    for name in os.listdir(hist_dir):
        m = re.fullmatch(r"match_(\d+)\.ndjson", name)
        if m and int(m.group(1)) not in keep:
            os.remove(os.path.join(hist_dir, name))


def write_csvs(summary: dict, parts_dir: str, run_dir: str, keep: set[int] | None = None) -> list[dict]:
    counts = {"bot_summary": write_rows(os.path.join(run_dir, "bot_summary.csv"), summary["bots"])}
    ser = summary["series"]
    counts["cumulative_winnings"] = write_rows(
        os.path.join(run_dir, "cumulative_winnings.csv"),
        [{"hand_index": x, **{f"{l}_bb": ser["lines"][l][i] for l in ser["lines"]}}
         for i, x in enumerate(ser["x"])])
    if summary.get("evaluation") and summary["evaluation"]["pairs"]:
        counts["comparisons"] = write_rows(os.path.join(run_dir, "comparisons.csv"),
                                           summary["evaluation"]["pairs"])
    counts.update(combine_parts(parts_dir, run_dir, keep))
    files = []
    for name in ["bot_summary", "comparisons", "matches", "hands", "actions", "pots", "cumulative_winnings", "errors"]:
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
    if not RUN_ID.fullmatch(run_id):
        return None
    path = os.path.join(out, run_id, "summary.json")
    if not os.path.isfile(path):
        return None
    with open(path) as f:
        return json.load(f)
