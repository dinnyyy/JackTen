"""All-in EV: the expected pot winnings of each player once the betting is over.

When every remaining bet is called and cards are still to come, who wins the
pot is pure luck. `expected_wins` averages the outcome over the possible
runouts (exact when two or fewer cards are to come, otherwise a fixed-seed
Monte Carlo sample). The difference `expected - actual` has mean zero, so
subtracting it from a hand's result removes that luck without adding bias:
this is the control variate used for the "EV" columns in the sim stats.
"""

import itertools
import random

from engine.evaluator import evaluate
from engine.pots import build_pots, award

MC_SAMPLES = 1000
EXACT_LIMIT = 2000   # enumerate when there are at most this many runouts


def expected_wins(snap: dict, seed, hand_number: int) -> dict[int, float]:
    """Expected chips won from the pots by each live seat, given a Hand.runout snapshot.

    Uncalled-bet returns are excluded (they are the same in every runout).
    The runout is uniform over the cards not in any hole hand or on the board.
    """
    board, holes, live = snap["board"], snap["holes"], set(snap["live"])
    pots, _ = build_pots(snap["contrib"], live)
    known = set(board) | {c for h in holes.values() for c in h}
    rest = [c for c in range(52) if c not in known]
    k = 5 - len(board)
    # any order works for odd chips; seats in numeric order keeps it deterministic
    order = sorted(holes)

    total_runouts = 1
    for i in range(k):
        total_runouts = total_runouts * (len(rest) - i) // (i + 1)
    if total_runouts <= EXACT_LIMIT:
        runouts = itertools.combinations(rest, k)
        n = total_runouts
    else:
        rng = random.Random(f"{seed}:{hand_number}:allin")
        runouts = (rng.sample(rest, k) for _ in range(MC_SAMPLES))
        n = MC_SAMPLES

    acc = dict.fromkeys(live, 0.0)
    for extra in runouts:
        full = board + list(extra)
        values = {s: evaluate(holes[s] + full) for s in live}
        for s, amt in award(pots, values, order).items():
            acc[s] += amt
    return {s: v / n for s, v in acc.items()}
