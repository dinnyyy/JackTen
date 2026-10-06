"""Engine rule tests. Run: python -m unittest discover tests"""

import random
import unittest

from engine.bots import RandomBot, CallerBot, RaiserBot, FolderBot
from engine.cards import parse_card
from engine.evaluator import evaluate, describe
from engine.hand import Hand
from engine.match import Match, MatchConfig, BlindLevel
from engine.pots import build_pots, award


def cs(s):
    return [parse_card(c) for c in s.split()]


def ev(s):
    return evaluate(cs(s))


def rigged_hand(stacks, holes, board, button=0, sb=50, bb=100, ante=0):
    """Hand with a fixed deal. holes: {seat: 'As Kd'}; board: 5 cards."""
    h = Hand(1, stacks, button, sb, bb, ante, random.Random(0))
    used = set()
    for s in holes:
        used |= set(cs(holes[s]))
    used |= set(cs(board))
    # deal order: 2 rounds from left of button, then burn+3, burn+1, burn+1
    order = h.order_after(button)
    deck = []
    filler = [c for c in range(52) if c not in used]
    for rnd in range(2):
        for s in order:
            deck.append(cs(holes[s])[rnd])
    b = cs(board)
    deck += [filler.pop(), *b[:3], filler.pop(), b[3], filler.pop(), b[4]]
    h.deck.cards = deck + filler
    return h


class TestEvaluator(unittest.TestCase):
    def test_category_order(self):
        hands = [
            "2c 7d 9h Jc Ks 3d 4h",     # high card
            "2c 2d 9h Jc Ks 3d 4h",     # pair
            "2c 2d 9h 9c Ks 3d 4h",     # two pair
            "2c 2d 2h 9c Ks 3d 4h",     # trips
            "5c 6d 7h 8c 9s 2d 2h",     # straight
            "2h 7h 9h Jh Kh 3d 4c",     # flush
            "2c 2d 2h 9c 9s 3d 4h",     # full house
            "2c 2d 2h 2s 9s 3d 4h",     # quads
            "5h 6h 7h 8h 9h 2d 2c",     # straight flush
        ]
        vals = [ev(h) for h in hands]
        self.assertEqual(vals, sorted(vals))
        self.assertEqual([v[0] for v in vals], list(range(9)))

    def test_wheel_and_broadway(self):
        self.assertEqual(ev("Ac 2d 3h 4c 5s 9d Jh"), (4, 3))
        self.assertGreater(ev("2c 3d 4h 5c 6s 9d Jh"), ev("Ac 2d 3h 4c 5s 9d Jh"))
        self.assertEqual(describe(ev("Th Jh Qh Kh Ah 2c 3d")), "royal flush")
        self.assertEqual(ev("Ah 2h 3h 4h 5h Kc Kd"), (8, 3))  # steel wheel

    def test_kickers(self):
        self.assertGreater(ev("Ac Ad Kh 9c 4s 3d 2h"), ev("As Ah Qh Jc 9s 3d 2h"))
        # two pair: best kicker can come from a third pair
        self.assertEqual(ev("Kc Kd 9h 9c 5s 5d 2h"), (2, 11, 7, 3))
        # two trips -> full house with the lower trips as the pair
        self.assertEqual(ev("Kc Kd Kh 9c 9s 9d 2h"), (6, 11, 7))

    def test_board_plays_tie(self):
        board = "Ac Kd Qh Jc Ts"
        self.assertEqual(evaluate(cs("2c 3d " + board)), evaluate(cs("4h 5s " + board)))

    def test_flush_beats_straight_with_both(self):
        self.assertEqual(ev("4h 5h 6h 7c 8h 2h 9d")[0], 5)


class TestPots(unittest.TestCase):
    def test_three_way_side_pots(self):
        # A all-in 100, B all-in 300, C covers with 500 (200 uncalled).
        pots, returns = build_pots({0: 100, 1: 300, 2: 500}, {0, 1, 2})
        self.assertEqual([(p.amount, p.eligible) for p in pots], [(300, [0, 1, 2]), (400, [1, 2])])
        self.assertEqual(returns, {2: 200})

    def test_folded_money_stays_in(self):
        pots, returns = build_pots({0: 400, 1: 400, 2: 150}, {0, 1})
        self.assertEqual([(p.amount, p.eligible) for p in pots], [(950, [0, 1])])
        self.assertEqual(returns, {})

    def test_odd_chip_left_of_button(self):
        pots, _ = build_pots({0: 101, 1: 101, 2: 101}, {0, 1, 2})
        won = award(pots, {0: (1,), 1: (5,), 2: (5,)}, seat_order=[2, 0, 1])
        self.assertEqual(won, {2: 152, 1: 151})

    def test_short_stack_wins_main_other_wins_side(self):
        pots, _ = build_pots({0: 100, 1: 300, 2: 300}, {0, 1, 2})
        won = award(pots, {0: (9,), 1: (5,), 2: (3,)}, seat_order=[0, 1, 2])
        self.assertEqual(won, {0: 300, 1: 400})


class TestBetting(unittest.TestCase):
    def test_heads_up_blinds_and_order(self):
        h = Hand(1, {0: 1000, 1: 1000}, button=0, small_blind=50, big_blind=100, ante=0,
                 rng=random.Random(1))
        h.start()
        self.assertEqual((h.sb_seat, h.bb_seat), (0, 1))
        self.assertEqual(h.to_act, 0)            # button acts first preflop
        h.apply(0, "call")
        self.assertEqual(h.to_act, 1)            # BB option
        h.apply(1, "check")
        self.assertEqual(h.street, "flop")
        self.assertEqual(h.to_act, 1)            # BB acts first postflop

    def test_min_raise_tracks_last_full_raise(self):
        h = Hand(1, {0: 10000, 1: 10000, 2: 10000}, 0, 50, 100, 0, random.Random(1))
        h.start()                                # UTG = seat 0 (button) 3-handed
        self.assertEqual(h.legal(0)["min_raise_to"], 200)
        h.apply(0, "raise", 350)                 # raise of 250
        self.assertEqual(h.legal(1)["min_raise_to"], 600)

    def test_short_all_in_does_not_reopen(self):
        # 0=button/UTG, 1=SB, 2=BB (short: 250 total)
        h = Hand(1, {0: 10000, 1: 10000, 2: 250}, 0, 50, 100, 0, random.Random(1))
        h.start()
        h.apply(0, "raise", 200)                 # full raise of 100
        h.apply(1, "call")
        h.apply(2, "raise", 250)                 # all-in +50: incomplete
        self.assertEqual(h.to_act, 0)
        self.assertNotIn("raise", h.legal(0)["legal_actions"])
        self.assertEqual(h.legal(0)["legal_actions"], ["fold", "call"])

    def _four_way(self, sb_stack):
        # button=0, SB=1, BB=2, UTG=3. Seat 0 has 260, seat 1 has `sb_stack`.
        h = Hand(1, {0: 260, 1: sb_stack, 2: 10000, 3: 10000}, 0, 50, 100, 0, random.Random(1))
        h.start()
        h.apply(3, "raise", 200)                 # full raise of 100
        h.apply(0, "raise", 260)                 # all-in +60: incomplete
        return h

    def test_cumulative_short_all_ins_below_full_raise(self):
        h = self._four_way(sb_stack=280)
        h.apply(1, "raise", 280)                 # all-in +20; cumulative +80 < 100
        h.apply(2, "call")
        self.assertEqual(h.to_act, 3)
        self.assertEqual(h.legal(3)["legal_actions"], ["fold", "call"])

    def test_cumulative_short_all_ins_reopen(self):
        h = self._four_way(sb_stack=330)
        h.apply(1, "raise", 330)                 # all-in +70; cumulative +130 >= 100
        self.assertIn("raise", h.legal(2)["legal_actions"])  # BB never acted
        h.apply(2, "call")
        self.assertIn("raise", h.legal(3)["legal_actions"])
        self.assertEqual(h.legal(3)["min_raise_to"], 430)    # last full raise is still 100

    def test_short_big_blind_keeps_full_call(self):
        h = Hand(1, {0: 1000, 1: 1000, 2: 60}, 0, 50, 100, 0, random.Random(1))
        h.start()
        self.assertTrue(h.players[2].all_in)
        self.assertEqual(h.legal(0)["to_call"], 100)

    def test_no_raise_when_everyone_else_all_in(self):
        h = Hand(1, {0: 1000, 1: 300}, 0, 50, 100, 0, random.Random(1))
        h.start()
        h.apply(0, "raise", 1000)
        h.apply(1, "call")                       # all-in for 300
        self.assertTrue(h.done)                  # ran out
        self.assertEqual(len(h.board), 5)
        self.assertEqual(sum(p.stack for p in h.players.values()), 1300)

    def test_uncalled_bet_returned(self):
        h = Hand(1, {0: 1000, 1: 1000}, 0, 50, 100, 0, random.Random(1))
        h.start()
        h.apply(0, "raise", 600)
        h.apply(1, "fold")
        self.assertEqual(h.players[0].stack, 1100)
        self.assertEqual(h.result["winners"], [{"seat": 0, "amount": 200}])
        self.assertEqual(h.result["uncalled_returned"], {"0": 500})

    def test_split_pot_with_side_pot(self):
        # seat 2 short all-in; seats 0 and 1 chop with the same straight, seat 2 loses
        h = rigged_hand({0: 1000, 1: 1000, 2: 300},
                        {0: "Ac 2d", 1: "As 3d", 2: "Kh Kd"},
                        board="Tc Jd Qh Ks 4c", button=0)
        h.start()
        h.apply(0, "raise", 300)
        h.apply(1, "call")
        h.apply(2, "call")                       # all-in 300
        # postflop 0 and 1 check it down
        while not h.done:
            h.apply(h.to_act, "check")
        self.assertEqual([p["amount"] for p in h.result["pots"]], [900])
        self.assertEqual(h.players[0].stack, 1000 - 300 + 450)
        self.assertEqual(h.players[1].stack, 1000 - 300 + 450)
        self.assertEqual(h.players[2].stack, 0)

    def test_ante_all_in(self):
        h = Hand(1, {0: 1000, 1: 1000, 2: 20}, 0, 50, 100, 25, random.Random(1))
        h.start()
        self.assertTrue(h.players[2].all_in)
        self.assertEqual(h.players[2].total, 20)

    def test_invalid_actions_are_corrected(self):
        h = Hand(1, {0: 1000, 1: 1000}, 0, 50, 100, 0, random.Random(1))
        h.start()
        ev_ = h.apply(0, "check")                # facing BB -> fold
        self.assertEqual(ev_[0]["action"], "fold")
        self.assertIn("corrected", ev_[0])


class TestMatch(unittest.TestCase):
    def test_chip_conservation_random(self):
        for seed in range(30):
            rng = random.Random(seed)
            n = rng.randint(2, 9)
            bots = [RandomBot(random.Random(seed * 100 + i)) for i in range(n)]
            cfg = MatchConfig(num_hands=200, starting_stack=2000, seed=seed, enforce_time=False,
                              blind_schedule=[BlindLevel(0, 10, 20, 0), BlindLevel(50, 25, 50, 5)])
            end = Match(bots, cfg).run()
            self.assertEqual(sum(end["final_stacks"].values()), 2000 * n)
            self.assertEqual(sorted(end["rankings"]), list(range(n)))

    def test_mixed_builtins(self):
        bots = [CallerBot(), RaiserBot(), FolderBot(), RandomBot(random.Random(3))]
        end = Match(bots, MatchConfig(num_hands=300, seed=7, enforce_time=False)).run()
        self.assertEqual(sum(end["final_stacks"].values()), 4 * 20000)


if __name__ == "__main__":
    unittest.main()
