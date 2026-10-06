"""Run many matches between bots and report statistics.

Examples:
    python simulate.py                                     # 6 random bots, 100 matches
    python simulate.py --bots random caller raiser folder --matches 500
    python simulate.py --bots "jackten=cmd:python my_bot.py" random random random

Each bot is `spec` or `label=spec`; bots sharing a label are pooled in the stats.
Seats are shuffled every match so no bot keeps a positional edge.

Writes to data/sims/<timestamp>/:
    summary.json / summary.csv   per-bot stats (bb/100 with 95% CI, VPIP, PFR, ...)
    matches.csv                  per-match final stacks and winner
    histories/match_XXXX.ndjson  full hand histories (skip with --no-log)

The same runs are browsable from the Simulate page in `python play.py`.
"""

import argparse
import sys

from engine.sim import DEFAULTS, run_simulation
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

    def progress(done, total, hands, elapsed):
        if done % step == 0 or done == total:
            print(f"  {done}/{total} matches  {hands} hands  ({elapsed:.1f}s)", flush=True)

    try:
        s = run_simulation(params, on_progress=progress)
    except ValueError as e:
        sys.exit(str(e))
    print(f"\n{s['total_hands']} hands in {s['elapsed_s']}s  (seed {s['params']['seed']})\n")
    print(format_table(s["bots"]))
    print(f"\nSaved to {s['dir']}")


if __name__ == "__main__":
    main()
