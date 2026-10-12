import unittest

from bot.exp_value import bbf, calc_ev, equity_to_call, ev_call, ev_raise, mdf, spr


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


if __name__ == "__main__":
    unittest.main()
