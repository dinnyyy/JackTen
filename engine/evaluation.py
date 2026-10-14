"""Phase 8 evaluation: win rates with honest confidence intervals, and fair comparisons.

Unit of analysis
    A *block* is 100 consecutive hands of one match. A block's rate is
    100 * (net big blinds of a bot's seats) / (seat-hands), i.e. bb/100. Hands in
    a match share stacks and bots' adaptation, so they are not independent;
    blocks are close enough to be, and
        SE = SD(block rates) / sqrt(number of blocks)
    is the standard error on bb/100. 95% CI half-width is 1.96 * SE.

Duplicate deals
    With `--duplicate` every deal seed is played several times with the bots moved
    between seats (two bots on three seats each: they swap; otherwise the table
    is rotated). Cards are seeded per hand number, so each play of a deal sees the
    same hole cards by seat. Each bot therefore holds every hand it is compared
    against, and the luck of the deal cancels. The independent unit becomes the
    (deal, block) pair, with the plays of that deal pooled.

All-in EV
    Every rate also comes in an "EV" version where all-in runouts are replaced by
    their expected value (engine/allin.py). Same mean in the long run, less noise.

Frozen benchmark seeds
    Seeds BENCH_SEED .. BENCH_SEED + BENCH_SPAN - 1 are reserved for final
    comparisons (`--bench`). Ordinary runs refuse them and never draw them at
    random, and every benchmark run is appended to `bench_log.jsonl`, so the
    number of times you have looked at them is on record. Tune on dev seeds only.
"""

import itertools
import json
import math
import os
import random
import time

from engine.stats import BLOCK

Z95 = 1.96
BENCH_SEED = 1_000_000_000
BENCH_SPAN = 1_000_000
METRICS = (("", 0), ("_ev", 1))   # (key suffix, index into a block cell)


# ---------- seeds ----------

def overlaps_bench(seed: int, n: int) -> bool:
    return seed < BENCH_SEED + BENCH_SPAN and seed + n > BENCH_SEED


def dev_seed(n: int) -> int:
    """A random seed whose deals [seed, seed + n) stay clear of the benchmark range."""
    while True:
        seed = random.randrange(2 ** 31)
        if not overlaps_bench(seed, n):
            return seed


def bench_log_path(out: str) -> str:
    return os.path.join(os.path.dirname(os.path.abspath(out)), "bench_log.jsonl")


def log_bench(out: str, entry: dict) -> None:
    with open(bench_log_path(out), "a") as f:
        f.write(json.dumps(entry) + "\n")


# ---------- duplicate seatings ----------

def plays_per_deal(lineup: list[tuple[str, str]]) -> int:
    labels = list(dict.fromkeys(l for l, _ in lineup))
    counts = {l: sum(1 for x, _ in lineup if x == l) for l in labels}
    if len(labels) == 2 and counts[labels[0]] == counts[labels[1]]:
        return 2
    return len(lineup)


def seatings(lineup: list[tuple[str, str]], rng: random.Random) -> list[list[tuple[str, str]]]:
    """Seat orders for the plays of one deal. The first is a random shuffle.

    Two labels with equal counts: the second play swaps them seat for seat.
    Anything else: the shuffled order is rotated one seat per play.
    """
    base = list(lineup)
    rng.shuffle(base)
    labels = list(dict.fromkeys(l for l, _ in lineup))
    if plays_per_deal(lineup) == 2 and len(labels) == 2:
        a, b = labels
        pool = {a: [e for e in lineup if e[0] == a], b: [e for e in lineup if e[0] == b]}
        used = {a: 0, b: 0}
        swapped = []
        for l, _ in base:
            other = b if l == a else a
            swapped.append(pool[other][used[other] % len(pool[other])])
            used[other] += 1
        return [base, swapped]
    return [base[k:] + base[:k] for k in range(len(base))]


# ---------- statistics ----------

def sd_of(xs: list[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    m = sum(xs) / n
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))


def ratio_ci(units: list[dict], plus: str, minus: str | None, i: int) -> tuple[float, float, float | None]:
    """bb/100 of `plus` (minus that of `minus`) over blocks, with its 95% half-width.

    A unit holds [bb, bb_ev, seat_hands] per label. The estimate is the ratio
    100 * sum(bb) / sum(seat_hands), so blocks cut short by a bust-out count in
    proportion to their length. Its standard error is the usual ratio-estimator
    linearisation, which for equal-sized blocks is exactly SD(block rates) / sqrt(n).
    Returns (estimate, half-width, z); z is None without a usable variance.
    """
    labels = [plus] + ([minus] if minus else [])
    sign = {plus: 1.0, minus: -1.0}
    est, den = {}, {}
    for l in labels:
        d = sum(u[l][2] for u in units)
        den[l] = d
        est[l] = sum(u[l][i] for u in units) / d if d else 0.0
    total = 100 * sum(sign[l] * est[l] for l in labels)
    n = len(units)
    if n < 2 or not all(den.values()):
        return total, 0.0, None
    ss = 0.0
    for u in units:
        r = sum(sign[l] * (u[l][i] - est[l] * u[l][2]) / den[l] for l in labels)
        ss += r * r
    se = 100 * math.sqrt(ss * n / (n - 1))
    return total, Z95 * se, (total / se if se else None)


def play_units(results: list[dict], labels: list[str], full_only: bool = False) -> list[dict]:
    """One unit per (match, block): label -> [bb, bb_ev, seat_hands]."""
    out = []
    for r in results:
        for blk, n in r["block_hands"].items():
            if full_only and n < BLOCK:
                continue
            cells = [r["blocks"].get(l, {}).get(blk) for l in labels]
            if all(c and c[2] for c in cells):
                out.append({l: list(c) for l, c in zip(labels, cells)})
    return out


def deal_units(results: list[dict], labels: list[str], plays: int) -> list[dict]:
    """One unit per (deal, block): the cells of all `plays` plays of that deal summed."""
    groups: dict[int, list[dict]] = {}
    for r in results:
        groups.setdefault(r["index"] // plays, []).append(r)
    out = []
    for rs in groups.values():
        if len(rs) < plays:
            continue                      # deal not fully played (cancelled run)
        for blk in set.intersection(*(set(r["block_hands"]) for r in rs)):
            unit = {}
            for l in labels:
                cells = [r["blocks"].get(l, {}).get(blk) for r in rs]
                if any(c is None or not c[2] for c in cells):
                    break
                unit[l] = [sum(c[i] for c in cells) for i in range(3)]
            else:
                out.append(unit)
    return out


def evaluate_results(results: list[dict], labels: list[str], plays: int = 1) -> dict:
    """Confidence intervals and pairwise comparisons from per-match block data.

    `plays` is the number of matches per deal seed (1 = no duplicate).
    Every figure is returned twice: realised results and all-in-EV (`_ev`).
    """
    singles = play_units(results, labels)
    full_singles = play_units(results, labels, full_only=True)
    units = deal_units(results, labels, plays) if plays > 1 else singles

    bots = {}
    for l in labels:
        d = {"blocks": len(units)}
        for suf, i in METRICS:
            est, ci, _ = ratio_ci(units, l, None, i)
            d["bb_per_100" + suf] = round(est, 2)
            d["ci95" + suf] = round(ci, 2)
        # SD of one full 100-hand block of one match: the "about 100 bb/100" figure
        full = [u[l] for u in full_singles]
        d["sd_100"] = round(sd_of([100 * c[0] / c[2] for c in full]), 1)
        d["sd_100_ev"] = round(sd_of([100 * c[1] / c[2] for c in full]), 1)
        bots[l] = d

    pairs = []
    for a, b in itertools.combinations(labels, 2):
        p = {"a": a, "b": b, "blocks": len(units)}
        for suf, i in METRICS:
            diff, ci, z = ratio_ci(units, a, b, i)
            p["diff" + suf] = round(diff, 2)
            p["ci95" + suf] = round(ci, 2)
            p["z" + suf] = None if z is None else round(z, 2)
            p["significant" + suf] = bool(ci and abs(diff) > ci)
            if plays > 1:   # the CI a non-duplicate run of the same size would have had
                p["ci95_nodup" + suf] = round(ratio_ci(singles, a, b, i)[1], 2)
        pairs.append(p)

    return {"block_hands": BLOCK, "plays_per_deal": plays, "units": len(units),
            "bots": bots, "pairs": pairs}


def format_pairs(ev: dict) -> str:
    """Pairwise comparison table (realised and EV), widest-first."""
    if not ev["pairs"]:
        return ""
    dup = ev["plays_per_deal"] > 1
    head = f"{'comparison':<24} {'diff bb/100':>12} {'+-95%':>7} {'EV diff':>9} {'+-95%':>7}"
    if dup:
        head += f" {'+-95% w/o dup':>14}"
    lines = [head, "-" * len(head)]
    for p in sorted(ev["pairs"], key=lambda p: -abs(p["diff_ev"])):
        name = f"{p['a']} - {p['b']}"[:24]
        mark = " *" if p["significant_ev"] else ""
        line = (f"{name:<24} {p['diff']:>+12.2f} {p['ci95']:>7.2f} {p['diff_ev']:>+9.2f} "
                f"{p['ci95_ev']:>7.2f}")
        if dup:
            line += f" {p['ci95_nodup_ev']:>14.2f}"
        lines.append(line + mark)
    lines.append(f"\n{ev['units']} {'(deal, block) units' if dup else 'blocks'} of {ev['block_hands']} hands; "
                 f"* = EV difference outside its 95% CI")
    return "\n".join(lines)


def timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")
