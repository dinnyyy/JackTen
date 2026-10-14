"""Run many matches between bots and report statistics.

Examples:
    python simulate.py                                     # 6 random bots, 100 matches
    python simulate.py --bots random caller raiser folder --matches 500
    python simulate.py --bots "jackten=cmd:python my_bot.py" random random random

Each bot is `spec` or `label=spec`; bots sharing a label are pooled in the stats.
Seats are shuffled every match so no bot keeps a positional edge.

Evaluation (Phase 8):
    --duplicate   replay every deal with the bots moved between seats (deal luck cancels)
    --cash        reset every stack after each hand (no bust-outs): hands are independent,
                  bb/100 is at a constant depth, and duplicate deals cancel the most luck
    --bench       frozen benchmark seeds for final comparisons (implies --duplicate --cash);
                  never tune on these
    The table shows bb/100 with a 95% CI built from 100-hand blocks, the same with
    all-in runouts replaced by their expected value (EV), and a pairwise comparison.

Writes to data/sims/<timestamp>/:
    summary.json / summary.csv   per-bot stats (bb/100 with 95% CI, VPIP, PFR, ...)
    matches.csv                  per-match final stacks and winner
    histories/match_XXXX.ndjson  full hand histories (skip with --no-log)

The same runs are browsable from the Simulate page in `python play.py`.
"""

import argparse
import sys

from engine.sim import DEFAULTS, run_simulation
from engine.evaluation import format_pairs
from engine.stats import format_table


def main():
    d = DEFAULTS
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bots", nargs="+", default=d["bots"])
    ap.add_argument("--matches", type=int, default=d["matches"])
    ap.add_argument("--hands", type=int, default=d["hands"], help="max hands per match")
    ap.add_argument("--stack", type=int, default=d["stack"])
    ap.add_argument("--sb", type=int, default=d["sb"])
    ap.add_argument("--bb", type=int, default=d["bb"])
    ap.add_argument("--ante", type=int, default=d["ante"])
    ap.add_argument("--blind-up", type=int, default=d["blind_up"], metavar="N",
                    help="double the blinds every N hands (0 = fixed blinds)")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--duplicate", action="store_true",
                    help="play each deal several times with the bots moved between seats")
    ap.add_argument("--cash", action="store_true",
                    help="reset stacks after every hand (independent hands, no bust-outs)")
    ap.add_argument("--bench", action="store_true",
                    help="frozen benchmark seeds, implies --duplicate --cash; logged in data/bench_log.jsonl")
    ap.add_argument("--workers", type=int, default=d["workers"])
    ap.add_argument("--time-ms", type=int, default=d["time_ms"], help="per-action time for external bots")
    ap.add_argument("--bank-ms", type=int, default=d["bank_ms"])
    ap.add_argument("--out", default=d["out"])
    ap.add_argument("--no-log", action="store_true", help="don't write hand histories")
    args = ap.parse_args()

    params = {k: v for k, v in vars(args).items() if k != "no_log"}
    params["log"] = not args.no_log
    print(f"{args.matches} matches x up to {args.hands} hands | {len(args.bots)} seats | "
          f"{args.workers} workers")
    step = max(1, args.matches // 10)

    last = [-1]

    def progress(done, total, hands, elapsed):
        if done != last[0] and (done % step == 0 or done == total):
            last[0] = done
            print(f"  {done}/{total} matches  {hands} hands  ({elapsed:.1f}s)", flush=True)

    try:
        s = run_simulation(params, on_progress=progress)
    except ValueError as e:
        sys.exit(str(e))
    print(f"\n{s['total_hands']} hands in {s['elapsed_s']}s  (seed {s['params']['seed']})\n")
    print(format_table(s["bots"]))
    pairs = format_pairs(s["evaluation"]) if s.get("evaluation") else ""
    if pairs:
        print("\n" + pairs)
    print(f"\nSaved to {s['dir']}")


if __name__ == "__main__":
    main()
