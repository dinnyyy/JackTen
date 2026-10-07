"""Phase 0 tests. Run: python -m unittest discover tests"""

import unittest

from bot.combinatorics import (ALL_COMBOS, CLASS_COMBOS, canonical_combo, class_combos, combo_class,
                           filter_range, live_combos, parse_cards, remaining_deck)


class TestCombinatorics(unittest.TestCase):
    def test_counts(self):
        self.assertEqual(len(ALL_COMBOS), 1326)
        self.assertEqual(len(set(ALL_COMBOS)), 1326)
        self.assertEqual(len(CLASS_COMBOS), 169)
        self.assertEqual(sum(len(v) for v in CLASS_COMBOS.values()), 1326)

    def test_class_sizes(self):
        sizes = {"AA": 6, "AKs": 4, "AKo": 12}
        for cls, n in sizes.items():
            self.assertEqual(len(class_combos(cls)), n)
        by_size = [len(v) for v in CLASS_COMBOS.values()]
        self.assertEqual((by_size.count(6), by_size.count(4), by_size.count(12)), (13, 78, 78))

    def test_combo_class_order_independent(self):
        a, b = parse_cards("Kd As")
        self.assertEqual(combo_class(a, b), "AKo")
        self.assertEqual(combo_class(b, a), "AKo")
        self.assertEqual(combo_class(*parse_cards("Ks As")), "AKs")
        self.assertEqual(combo_class(*parse_cards("7h 7c")), "77")
        self.assertEqual(combo_class(*parse_cards("2c 3c")), "32s")

    def test_remaining_deck(self):
        hole, board = parse_cards("As Kd"), parse_cards("2c 3c 4c")
        deck = remaining_deck(hole, board)
        self.assertEqual(len(deck), 47)
        self.assertFalse(set(deck) & set(hole + board))

    def test_live_combos(self):
        self.assertEqual(len(live_combos()), 1326)
        self.assertEqual(len(live_combos(parse_cards("As Kd"))), 1225)           # C(50,2)
        self.assertEqual(len(live_combos(parse_cards("As Kd"), parse_cards("2c 3c 4c"))), 1081)  # C(47,2)
        self.assertEqual(len(live_combos(parse_cards("As Kd"), parse_cards("2c 3c 4c 5c 6c"))), 990)  # C(45,2)

    def test_filter_range(self):
        rng = {canonical_combo(*parse_cards("As Ah")): 1.0, canonical_combo(*parse_cards("Kd Kc")): 0.5}
        out = filter_range(rng, parse_cards("As"))
        self.assertEqual(list(out.values()), [0.5])

    def test_canonical_combo_rejects_duplicate(self):
        with self.assertRaises(ValueError):
            canonical_combo(5, 5)


if __name__ == "__main__":
    unittest.main()
