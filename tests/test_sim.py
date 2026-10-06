"""Simulation + CSV export tests. Run: python -m unittest discover tests"""

import csv
import os
import tempfile
import unittest
from collections import defaultdict

from engine.export import positions
from engine.sim import run_simulation


def read(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


class TestPositions(unittest.TestCase):
    def test_names(self):
        self.assertEqual(positions([0, 1], 0), {0: "BTN", 1: "BB"})
        self.assertEqual(positions([0, 1, 2], 0), {1: "SB", 2: "BB", 0: "BTN"})
        six = positions([0, 1, 2, 3, 4, 5], 5)
        self.assertEqual([six[s] for s in range(6)], ["SB", "BB", "UTG", "HJ", "CO", "BTN"])
        nine = positions(list(range(9)), 0)
        self.assertEqual([nine[s] for s in range(1, 9)] + [nine[0]],
                         ["SB", "BB", "UTG", "UTG+1", "UTG+2", "LJ", "HJ", "CO", "BTN"])


class TestSimExport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.s = run_simulation({"bots": ["random", "caller", "raiser", "folder"], "matches": 6,
                                "hands": 60, "seed": 5, "workers": 2, "out": cls.tmp.name,
                                "stack": 3000, "ante": 5})
        cls.dir = cls.s["dir"]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_files_listed_and_present(self):
        names = {f["name"] for f in self.s["files"]}
        for n in ("bot_summary.csv", "matches.csv", "hands.csv", "actions.csv", "pots.csv",
                  "cumulative_winnings.csv", "errors.csv"):
            self.assertIn(n, names)
            self.assertTrue(os.path.isfile(os.path.join(self.dir, n)))
        self.assertFalse(os.path.exists(os.path.join(self.dir, "parts")))

    def test_row_counts_match_listing(self):
        for f in self.s["files"]:
            self.assertEqual(len(read(os.path.join(self.dir, f["name"]))), f["rows"], f["name"])

    def test_hands_zero_sum_and_match_totals(self):
        hands = read(os.path.join(self.dir, "hands.csv"))
        per_hand = defaultdict(int)
        for r in hands:
            per_hand[(r["match"], r["hand"])] += int(r["net_chips"])
        self.assertTrue(all(v == 0 for v in per_hand.values()))
        self.assertEqual(len(per_hand), self.s["total_hands"])
        matches = read(os.path.join(self.dir, "matches.csv"))
        self.assertEqual(len(matches), 6 * 4)
        for m in {r["match"] for r in matches}:
            rows = [r for r in matches if r["match"] == m]
            self.assertEqual(sum(int(r["final_stack"]) for r in rows), 4 * 3000)

    def test_actions_consistent_with_pot(self):
        for r in read(os.path.join(self.dir, "actions.csv")):
            self.assertEqual(int(r["pot_after"]) - int(r["pot_before"]), int(r["chips_added"]))
            self.assertIn(r["action"], r["legal_actions"].split("|") + ["check", "fold"])

    def test_pots_sum_to_winnings(self):
        pots = read(os.path.join(self.dir, "pots.csv"))
        won = defaultdict(int)
        for r in read(os.path.join(self.dir, "hands.csv")):
            won[(r["match"], r["hand"])] += int(r["won_chips"])
        total = defaultdict(int)
        for p in pots:
            total[(p["match"], p["hand"])] += int(p["amount"])
        self.assertEqual(dict(total), {k: v for k, v in won.items() if v})


if __name__ == "__main__":
    unittest.main()
