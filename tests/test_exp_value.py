import unittest

from bot.exp_value import bbf, calc_ev, equity_to_call, equity_when_called, ev_call, ev_raise, mdf, position, realisation, spr


class TestExpValue(unittest.TestCase):
    def test_equity_to_call(self):
        self.assertAlmostEqual(equity_to_call(50, 100), 1 / 3)

    def test_ev_call_hand_checked(self):
        self.assertAlmostEqual(ev_call(100, 50, 0.30), -5.0)
        self.assertAlmostEqual(ev_call(100, 50, 0.40), 10.0)

    def test_fold_weak_hand_facing_bet(self):
        action, amt = calc_ev(100, 50, 0.05, ["fold", "call", "raise"], 100, 5000)
        self.assertEqual((action, amt), ("fold", None))

    def test_never_folds_when_free(self):
        action, _ = calc_ev(100, 0, 0.0, ["check", "raise"], 100, 5000)
        self.assertNotEqual(action, "fold")

    def test_check_not_call_when_free(self):
        action, amt = calc_ev(100, 0, 0.10, ["check"], 0, 0)
        self.assertEqual((action, amt), ("check", None))

    def test_strong_hand_raises_within_bounds(self):
        action, amt = calc_ev(100, 0, 0.9, ["check", "raise"], 100, 150)
        self.assertEqual(action, "raise")
        self.assertTrue(100 <= amt <= 150)

    def test_no_raise_when_illegal(self):
        action, _ = calc_ev(100, 50, 0.95, ["fold", "call"], None, None)
        self.assertEqual(action, "call")

    def test_bbf_and_mdf_sum_to_one(self):
        for rake in (0.0, 0.05):
            self.assertAlmostEqual(bbf(50, 100, rake) + mdf(50, 100, rake), 1.0)

    def test_bbf_values(self):
        self.assertAlmostEqual(bbf(50, 100), 1 / 3)
        self.assertAlmostEqual(bbf(100, 100), 0.5)

    def test_spr(self):
        self.assertAlmostEqual(spr(1000, 200), 5.0)

    def test_pure_bluff_breaks_even_at_bbf(self):
        import bot.exp_value as ev
        old = ev.fold_prob
        try:
            ev.fold_prob = lambda pot, bet: bbf(bet, pot, 0.05)
            self.assertAlmostEqual(ev_raise(100, 0, 0.0, 75, rake=0.05), 0.0)
        finally:
            ev.fold_prob = old

    def test_zero_rake_changes_nothing(self):
        self.assertEqual(ev_call(100, 50, 0.4, rake=0.0), ev_call(100, 50, 0.4))
        self.assertEqual(equity_to_call(50, 100, 0.0), equity_to_call(50, 100))

    def test_rake_makes_calls_worse(self):
        self.assertLess(ev_call(100, 50, 0.4, rake=0.05), ev_call(100, 50, 0.4))
        self.assertGreater(equity_to_call(50, 100, 0.05), equity_to_call(50, 100))

    def test_equity_when_called(self):
        self.assertEqual(equity_when_called(0.2, 1 / 3), 0.0)         # a bluff wins nothing when called
        self.assertAlmostEqual(equity_when_called(0.5, 0.5), 0.0)
        self.assertAlmostEqual(equity_when_called(1.0, 0.5), 1.0)
        self.assertAlmostEqual(equity_when_called(0.75, 0.5), 0.5)

    def test_weak_hands_do_not_bluff_raise(self):
        for e in (0.0, 0.05, 0.1, 0.3):
            action, _ = calc_ev(1000, 0, e, ["check", "raise"], 200, 100000)
            self.assertEqual(action, "check")

    def test_spr_zero_pot(self):
        self.assertEqual(spr(1000, 0), float("inf"))



class TestMultiwayBluff(unittest.TestCase):
    def test_one_opponent_matches_old_behaviour(self):
        self.assertEqual(ev_raise(100, 0, 0.3, 75), ev_raise(100, 0, 0.3, 75, opponents=1))

    def test_everyone_must_fold(self):
        # pot-sized bet: each folds 1/2 (bbf = 100/200), so three fold together 1/8
        from bot.exp_value import fold_prob
        self.assertAlmostEqual(fold_prob(100, 100) ** 3, 1 / 8)

    def test_bluff_profitable_heads_up_not_three_way(self):
        # pure bluff at exactly bbf breaks even heads-up and loses with more opponents
        self.assertAlmostEqual(ev_raise(100, 0, 0.0, 100, opponents=1), 0.0)
        self.assertLess(ev_raise(100, 0, 0.0, 100, opponents=3), 0.0)

    def test_called_equity_uses_per_opponent_fold(self):
        # pot-sized bet, 3 opponents: each folds 1/2, all fold 1/8; a caller is still the top half of a range
        pot, r, eq = 100, 100, 0.6
        f = 0.5 ** 3
        e = equity_when_called(eq, 0.5)
        want = f * pot + (1 - f) * (e * (pot + r) - (1 - e) * r)
        self.assertAlmostEqual(ev_raise(pot, 0, eq, r, opponents=3), want)

    def test_nuts_still_raises_multiway(self):
        action, _ = calc_ev(100, 0, 0.95, ["check", "raise"], 100, 5000, 4)
        self.assertEqual(action, "raise")


class TestRealisation(unittest.TestCase):
    def test_position_six_handed(self):
        # button on 3: order is 4, 5, 0, 1, 2, 3
        self.assertEqual(position(4, 3, range(6)), 0.0)
        self.assertEqual(position(3, 3, range(6)), 1.0)
        self.assertAlmostEqual(position(1, 3, range(6)), 0.6)

    def test_position_skips_busted_seats_and_heads_up(self):
        self.assertEqual(position(5, 0, [0, 2, 5]), 0.5)
        self.assertEqual(position(0, 0, [0, 2]), 1.0)
        self.assertEqual(position(2, 0, [0, 2]), 0.0)

    def test_realisation_directions(self):
        base = realisation(1.0, 1, 0.0, 0.0)
        self.assertEqual(base, 1.0)
        self.assertLess(realisation(0.0, 1, 0, 0), base)
        self.assertLess(realisation(1.0, 3, 0, 0), base)
        self.assertLess(realisation(1.0, 1, 0, 0.3), base)
        # a draw only pays for position when out of position
        self.assertEqual(realisation(1.0, 1, 0.35, 0), 1.0)
        self.assertLess(realisation(0.0, 1, 0.35, 0), realisation(0.0, 1, 0, 0))

    def test_realisation_clamped(self):
        self.assertEqual(realisation(0.0, 9, 1.0, 1.0), 0.6)

if __name__ == "__main__":
    unittest.main()
