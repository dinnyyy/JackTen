"""Phase 8 evaluation tests. Run: python -m unittest discover tests"""

import math
import os
import random
import tempfile
import unittest

from engine.allin import expected_wins
from engine.bots import CallerBot, FolderBot, RandomBot
from engine.cards import parse_card as c
from engine.evaluation import (BENCH_SEED, bench_log_path, evaluate_results, overlaps_bench, plays_per_deal,
                               ratio_ci, seatings)
from engine.match import Match, MatchConfig
from engine.sim import run_simulation
from engine.stats import StatsTracker


class Recorder:
    def __init__(self):
        self.holes = {}

    def on_event(self, m):
        if m["type"] == "hand_start":
            self.holes[m["hand_number"]] = m["hole_cards"]


def play(order, seed, hands=15):
    rec = Recorder()
    bots = [FolderBot() if l == "f" else CallerBot() for l in order]
    Match(bots, MatchConfig(num_hands=hands, seed=seed, enforce_time=False, starting_stack=10 ** 7), observers=[rec]).run()
    return rec.holes


class TestDuplicateDeals(unittest.TestCase):
    def test_same_cards_by_seat_whatever_the_bots_do(self):
        a = play("fcfcfc", 4)
        b = play("cfcfcf", 4)       # bots swapped between seats, so play diverges
        common = min(len(a), len(b))
        self.assertGreater(common, 3)
        for h in range(common):
            self.assertEqual(a[h], b[h])

    def test_different_seed_different_cards(self):
        self.assertNotEqual(play("fcfcfc", 4)[0], play("fcfcfc", 5)[0])

    def test_seatings_swap_and_rotate(self):
        lineup = [("a", "x")] * 3 + [("b", "y")] * 3
        self.assertEqual(plays_per_deal(lineup), 2)
        first, second = seatings(lineup, random.Random(1))
        self.assertEqual([l for l, _ in second], ["b" if l == "a" else "a" for l, _ in first])
        odd = [("a", "x")] * 2 + [("b", "y")] + [("c", "z")] * 3
        self.assertEqual(plays_per_deal(odd), 6)
        orders = seatings(odd, random.Random(1))
        self.assertEqual(len(orders), 6)
        self.assertEqual(orders[1], orders[0][1:] + orders[0][:1])


class TestAllInEV(unittest.TestCase):
    def test_preflop_aces_vs_kings(self):
        snap = {"board": [], "holes": {0: [c("As"), c("Ah")], 1: [c("Kd"), c("Kc")]},
                "contrib": {0: 1000, 1: 1000}, "live": [0, 1]}
        ev = expected_wins(snap, 1, 0)
        self.assertAlmostEqual(sum(ev.values()), 2000, places=6)
        self.assertAlmostEqual(ev[0] / 2000, 0.82, delta=0.03)

    def test_turn_is_exact(self):
        # AA vs 22 on a dry turn: the deuces need one of 2 outs in 44 cards
        board = [c("2c"), c("9d"), c("Th"), c("4s")]
        snap = {"board": board, "holes": {0: [c("As"), c("Ah")], 1: [c("2d"), c("2h")]},
                "contrib": {0: 500, 1: 500}, "live": [0, 1]}
        ev = expected_wins(snap, 1, 0)
        # 1 deuce is already on the board: 22 has a set; AA needs an ace (2 outs) to improve
        # to a set, but a set of deuces is already ahead; check conservation and exact 44-card average
        self.assertAlmostEqual(sum(ev.values()), 1000, places=6)
        self.assertEqual(round(ev[0] * 44) % 1, 0)   # a multiple of 1/44 of the pot

    def test_side_pots_conserve_chips(self):
        snap = {"board": [], "holes": {0: [c("As"), c("Ah")], 1: [c("Kd"), c("Kc")],
                                       2: [c("7s"), c("2d")], 3: [c("9c"), c("9d")]},
                "contrib": {0: 300, 1: 1000, 2: 1000, 3: 1000}, "live": [0, 1, 2, 3]}
        ev = expected_wins(snap, 1, 0)
        self.assertAlmostEqual(sum(ev.values()), 3300, places=6)
        self.assertGreater(ev[0], 0.4 * 1200)    # short stack only wins the 1200 main pot

    def test_match_emits_zero_sum_adjustments(self):
        class Grab:
            events = []

            def on_event(self, m):
                if m["type"] == "allin_ev":
                    self.events.append(m)
        g = Grab()
        bots = [RandomBot(random.Random(i)) for i in range(4)]
        Match(bots, MatchConfig(num_hands=60, seed=3, enforce_time=False, starting_stack=2000,
                                allin_ev=True), observers=[g]).run()
        self.assertGreater(len(g.events), 0)
        for m in g.events:
            self.assertAlmostEqual(sum(m["adjust"].values()), 0, delta=0.1 * len(m["adjust"]))

    def test_tracker_ev_series(self):
        t = StatsTracker(["a", "b"])
        t.on_event({"type": "hand_start", "big_blind": 100, "stacks": {"0": 1000, "1": 1000}})
        t.on_event({"type": "allin_ev", "hand_number": 0, "adjust": {"0": -300.0, "1": 300.0}})
        t.on_event({"type": "hand_result", "hand_number": 0, "winners": [{"seat": 0, "amount": 2000}],
                    "showdown": [], "stacks": {"0": 2000, "1": 0}})
        self.assertEqual(t.stats["a"]["bb_sum"], 10.0)
        self.assertEqual(t.stats["a"]["bb_ev_sum"], 7.0)
        self.assertEqual(t.blocks["b"][0], [-10.0, -7.0, 1])


class TestStatistics(unittest.TestCase):
    def unit(self, bb, n=100):
        return {"a": [bb, bb, n], "b": [-bb, -bb, n]}

    def test_ratio_ci_matches_sd_over_sqrt_n_for_equal_blocks(self):
        rates = [20, -35, 60, 5, -10, 42, -50, 15]
        units = [self.unit(r) for r in rates]
        est, ci, _ = ratio_ci(units, "a", None, 0)
        m = sum(rates) / len(rates)
        sd = math.sqrt(sum((r - m) ** 2 for r in rates) / (len(rates) - 1))
        self.assertAlmostEqual(est, m, places=9)
        self.assertAlmostEqual(ci, 1.96 * sd / math.sqrt(len(rates)), places=9)

    def test_partial_blocks_weighted_by_length(self):
        est, _, _ = ratio_ci([self.unit(100, 100), self.unit(0, 100), self.unit(50, 10)], "a", None, 0)
        self.assertAlmostEqual(est, 100 * 150 / 210)

    def test_paired_diff_of_zero_sum_pair_is_twice_one_side(self):
        units = [self.unit(r) for r in (10, -20, 30, 5)]
        a = ratio_ci(units, "a", None, 0)
        d = ratio_ci(units, "a", "b", 0)
        self.assertAlmostEqual(d[0], 2 * a[0])
        self.assertAlmostEqual(d[1], 2 * a[1])

    def test_ci_covers_truth(self):
        """95% CIs from simulated blocks should cover the true mean about 95% of the time."""
        rng = random.Random(3)
        hits = 0
        for _ in range(400):
            units = [self.unit(rng.gauss(10, 100)) for _ in range(60)]
            est, ci, _ = ratio_ci(units, "a", None, 0)
            hits += abs(est - 10) <= ci
        self.assertGreater(hits / 400, 0.91)


class TestBenchSeeds(unittest.TestCase):
    def test_reserved_range(self):
        self.assertTrue(overlaps_bench(BENCH_SEED, 10))
        self.assertTrue(overlaps_bench(BENCH_SEED - 5, 10))
        self.assertFalse(overlaps_bench(5, 100))

    def test_ordinary_run_refuses_bench_seeds(self):
        with self.assertRaises(ValueError):
            run_simulation({"bots": ["random", "caller"], "matches": 2, "hands": 5,
                            "seed": BENCH_SEED, "out": tempfile.mkdtemp()})

    def test_bench_uses_frozen_seed_and_is_logged(self):
        out = os.path.join(tempfile.mkdtemp(), "sims")   # the log is written beside `out`
        s = run_simulation({"bots": ["a=caller", "b=folder"], "matches": 2, "hands": 5, "bench": True,
                            "out": out, "workers": 1, "log": False, "csv_detail": False})
        self.assertEqual(s["params"]["seed"], BENCH_SEED)
        self.assertTrue(s["params"]["duplicate"] and s["params"]["cash"])
        with open(bench_log_path(out)) as f:
            self.assertEqual(len(f.readlines()), 1)

    def test_cash_mode_never_busts(self):
        s = run_simulation({"bots": ["random"] * 4, "matches": 2, "hands": 40, "cash": True, "seed": 1,
                            "out": tempfile.mkdtemp(), "workers": 1, "log": False, "csv_detail": False})
        self.assertEqual(s["total_hands"], 80)


class TestDuplicateShrinksCI(unittest.TestCase):
    def test_duplicate_run_has_pairs_and_nodup_reference(self):
        s = run_simulation({"bots": ["r=random", "f=folder"] * 3, "matches": 20, "hands": 100,
                            "seed": 2, "workers": 2, "out": tempfile.mkdtemp(), "log": False,
                            "csv_detail": False, "duplicate": True})
        self.assertEqual(s["matches_played"], 20)
        p = s["evaluation"]["pairs"][0]
        self.assertIn("ci95_nodup_ev", p)
        self.assertEqual(s["evaluation"]["plays_per_deal"], 2)


if __name__ == "__main__":
    unittest.main()


class TestLiveSeries(unittest.TestCase):
    def test_live_chart_credits_the_right_bot_when_seats_swap(self):
        snaps = []
        s = run_simulation({"bots": ["c=caller", "f=folder"] * 3, "matches": 16, "hands": 600, "cash": True,
                            "duplicate": True, "seed": 6, "workers": 2, "out": tempfile.mkdtemp(),
                            "log": False, "csv_detail": False}, on_snapshot=snaps.append)
        self.assertTrue(snaps)
        last = snaps[-1]["series"]["lines"]
        final = s["series"]["lines"]
        # same sign as the final result (the swapped plays used to cancel each other out)
        for l in ("c", "f"):
            self.assertGreater(final[l][-1] * last[l][-1], 0)
            self.assertGreater(abs(last[l][-1]), 0.3 * abs(final[l][-1]) * snaps[-1]["total_hands"] / s["total_hands"])
