import unittest

from bot.exp_value import calc_ev, equity_to_call, ev_call


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


if __name__ == "__main__":
    unittest.main()
