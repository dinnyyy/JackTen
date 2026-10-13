"""Equity and bot-decision tests. Run: python -m unittest discover tests"""

import math
import random
import unittest

from bot.combinatorics import parse_cards
from bot.equity import equity_exact, equity_monte_carlo, showdown
from engine.evaluator import evaluate
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

    def test_potential_flush_draw_and_made_hand(self):
        # flush draw on the flop: behind often, improves often; no outs from a monster
        _, _, ppot, npot = equity_monte_carlo(parse_cards("As Ks"), parse_cards("Qs 7s 2d"), 6000, random.Random(3), potential=True)
        self.assertGreater(ppot, 0.3)
        _, _, ppot2, npot2 = equity_monte_carlo(parse_cards("Ah Ad"), parse_cards("As Ac 2d"), 6000, random.Random(3), potential=True)
        self.assertLess(npot2, 0.05)

    def test_potential_matches_equity_and_rejects_preflop(self):
        hero, board = parse_cards("Ks Qd"), parse_cards("Kh 7d 2c 9s")
        eq, se, _, _ = equity_monte_carlo(hero, board, 4000, random.Random(5), potential=True)
        self.assertLess(abs(eq - equity_exact(hero, board)), 3 * se)
        with self.assertRaises(ValueError):
            equity_monte_carlo(hero, [], 10, potential=True)

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

    def test_target_se_stops_early_and_hits_target(self):
        class Counting(random.Random):
            calls = 0

            def choice(self, seq):
                self.calls += 1
                return super().choice(seq)

        lopsided, close = Counting(4), Counting(4)
        _, se_a = equity_monte_carlo(parse_cards("Ah As"), [], 20000, lopsided, target_se=0.01)
        _, se_b = equity_monte_carlo(parse_cards("Kh 7s"), [], 20000, close, target_se=0.01)
        self.assertLess(lopsided.calls, close.calls)
        self.assertLessEqual(lopsided.calls, 20000)
        self.assertLess(close.calls, 20000)
        self.assertLessEqual(se_a, 0.01)
        self.assertLessEqual(se_b, 0.0105)

    def test_target_se_caps_at_n(self):
        c = random.Random(1)
        _, se = equity_monte_carlo(parse_cards("Kh 7s"), [], 400, c, target_se=0.0001)
        self.assertGreater(se, 0.0001)

    def test_target_se_with_potential(self):
        out = equity_monte_carlo(parse_cards("9s 8s"), parse_cards("Qs 7s 2d"), 5000, random.Random(2),
                                 potential=True, target_se=0.01)
        self.assertEqual(len(out), 4)
        self.assertLessEqual(out[1], 0.0105)

    def test_read_hand_exact_on_river_sampled_on_turn(self):
        p = Player()
        p.rng = random.Random(2)
        hero = parse_cards("As Ah")
        self.assertEqual(p.read_hand(hero, parse_cards("2c 7d 9h Js 3c")), (equity_exact(hero, parse_cards("2c 7d 9h Js 3c")), 0.0, 0.0))
        eq, ppot, npot = p.read_hand(hero, parse_cards("2c 7d 9h Js"))
        self.assertLess(abs(eq - 0.84879), 0.03)
        self.assertGreater(npot, 0)


class TestMultiway(unittest.TestCase):
    def test_aa_three_way_about_73(self):
        eq, se = equity_monte_carlo(parse_cards("Ah As"), [], 20000, random.Random(1), players_left=2)
        self.assertLess(abs(eq - 0.734), 4 * se)

    def test_equity_falls_with_more_opponents(self):
        hero = parse_cards("Kh Qh")
        eqs = [equity_monte_carlo(hero, [], 6000, random.Random(2), players_left=k)[0] for k in (1, 2, 3, 5)]
        self.assertEqual(eqs, sorted(eqs, reverse=True))

    def test_three_way_tie_splits_pot(self):
        # board plays: everyone has the same straight
        board = parse_cards("5c 6d 7h 8s 9c")
        score = evaluate(parse_cards("2c 3d") + board)
        self.assertAlmostEqual(showdown(score, [parse_cards("2h 3h"), parse_cards("2s 3s")], board), 1 / 3)

    def test_ranges_pin_the_opponents(self):
        aa = {tuple(sorted(c)): 1 for c in [tuple(parse_cards("Ad Ac"))]}
        deuces = {tuple(sorted(tuple(parse_cards("2d 2c")))): 1}
        hero = parse_cards("Ks Kd")
        vs_aa, _ = equity_monte_carlo(hero, [], 4000, random.Random(3), ranges=[aa])
        vs_22, _ = equity_monte_carlo(hero, [], 4000, random.Random(3), ranges=[deuces])
        self.assertLess(vs_aa, 0.25)
        self.assertGreater(vs_22, 0.75)
        both, _ = equity_monte_carlo(hero, [], 4000, random.Random(3), ranges=[aa, deuces])
        self.assertLess(both, 0.25)  # still crushed by AA, and a second opponent cannot help

    def test_overlapping_ranges_never_share_cards(self):
        pair = {tuple(sorted(tuple(parse_cards("2d 2c")))): 1}
        with self.assertRaises(ValueError):
            equity_monte_carlo(parse_cards("Ks Kd"), [], 10, random.Random(1), ranges=[pair, pair])

    def test_potential_works_multiway(self):
        out = equity_monte_carlo(parse_cards("As Ks"), parse_cards("Qs 7s 2d"), 3000, random.Random(3),
                                 players_left=3, potential=True)
        self.assertGreater(out[2], 0.2)

    def test_fold_count_uses_cumulative_history(self):
        p = Player()
        p.num_players, p.seat = 4, 0
        p.rng = random.Random(1)
        hist = [{"seat": 2, "action": "fold"}, {"seat": 3, "action": "raise"}]
        req = {"board": [], "pot": 300, "to_call": 100, "min_raise_to": 200, "max_raise_to": 5000,
               "legal_actions": ["fold", "call", "raise"], "action_history": hist}
        p.hand = ["As", "Ah"]
        p.decide(req)
        p.decide(req)
        self.assertEqual(p.players_left, 2)


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

