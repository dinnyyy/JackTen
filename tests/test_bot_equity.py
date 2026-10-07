"""Equity and bot-decision tests. Run: python -m unittest discover tests"""

import math
import random
import unittest

from bot.combinatorics import parse_cards
from bot.equity import equity_exact, equity_monte_carlo, estimate_equity
from bot.player import Player


class TestEquity(unittest.TestCase):
    def test_nuts_on_river_is_one(self):
        # royal flush draw completed: hero holds the nuts
        self.assertEqual(equity_exact(parse_cards("As Ks"), parse_cards("Qs Js Ts 2d 3c")), 1.0)

    def test_river_hand_checked_by_count(self):
        # hero AA, board 2c 7d 9h Js 3c: only a pair of jacks or better in the opponent hand wins,
        # computed independently: 0.87727... (1 - 123/990 hands that win or tie, counted by hand)
        eq = equity_exact(parse_cards("As Ah"), parse_cards("2c 7d 9h Js 3c"))
        self.assertAlmostEqual(eq, 0.8772727, places=6)

    def test_monte_carlo_matches_exact_within_two_se(self):
        hero, board = parse_cards("Ks Qd"), parse_cards("Kh 7d 2c 9s")
        exact = equity_exact(hero, board)
        eq, se = equity_monte_carlo(hero, board, 4000, random.Random(7))
        self.assertLess(abs(eq - exact), 2 * se + 1e-9)

    def test_aa_preflop_about_85(self):
        eq, se = equity_monte_carlo(parse_cards("Ah As"), [], 10000, random.Random(1))
        self.assertLess(abs(eq - 0.852), 4 * se)

    def test_se_shrinks_as_root_n(self):
        hero = parse_cards("Jh Td")
        _, se1 = equity_monte_carlo(hero, [], 1000, random.Random(3))
        _, se4 = equity_monte_carlo(hero, [], 4000, random.Random(3))
        self.assertAlmostEqual(se1 / se4, 2.0, delta=0.2)

    def test_seeded_runs_repeat(self):
        hero = parse_cards("9h 9d")
        a = equity_monte_carlo(hero, [], 500, random.Random(5))
        b = equity_monte_carlo(hero, [], 500, random.Random(5))
        self.assertEqual(a, b)

    def test_estimate_exact_on_river_sampled_on_turn(self):
        hero = parse_cards("As Ah")
        eq, se = estimate_equity(hero, parse_cards("2c 7d 9h Js 3c"))
        self.assertEqual((se, round(eq, 4)), (0.0, 0.8773))
        eq, se = estimate_equity(hero, parse_cards("2c 7d 9h Js"), random.Random(2))
        self.assertGreater(se, 0)
        self.assertLess(abs(eq - 0.84879), 3 * se)


class TestDecide(unittest.TestCase):
    def setUp(self):
        self.p = Player()
        self.p.rng = random.Random(1)

    def req(self, hand, board, to_call, pot=1000, legal=None):
        self.p.hand = hand
        return {"board": board, "pot": pot, "to_call": to_call, "min_raise_to": 400,
                "max_raise_to": 20000,
                "legal_actions": legal or (["fold", "call", "raise"] if to_call else ["check", "raise"])}

    def test_folds_trash_facing_big_bet(self):
        r = self.p.decide(self.req(["7c", "2d"], ["As", "Kh", "Qd", "9s"], to_call=1000))
        self.assertEqual(r["action"], "fold")

    def test_raises_the_nuts(self):
        r = self.p.decide(self.req(["As", "Ks"], ["Qs", "Js", "Ts", "2d", "3c"], to_call=0))
        self.assertEqual(r["action"], "raise")
        self.assertTrue(400 <= r["amount"] <= 20000)

    def test_checks_weak_hand_when_free(self):
        r = self.p.decide(self.req(["7c", "2d"], ["As", "Kh", "Qd", "9s"], to_call=0))
        self.assertEqual(r["action"], "check")

    def test_calls_when_odds_are_good(self):
        # medium hand, tiny bet into a big pot: price is far below equity
        r = self.p.decide(self.req(["Th", "9d"], ["Tc", "4d", "2s", "7h"], to_call=50, pot=2000,
                                   legal=["fold", "call"]))
        self.assertEqual(r["action"], "call")


if __name__ == "__main__":
    unittest.main()
