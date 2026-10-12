import random

from bot.combinatorics import parse_cards
from bot.equity import equity_exact, equity_monte_carlo
from bot.exp_value import calc_ev

TARGET_SE = 0.01      # stop sampling once equity's standard error is this small
N_MAX = 10000         # cap on samples per decision


class Player:
    def __init__(self, stack: int = 0):
        self.rng = random.Random()
        self.hand = []

    def new_hand(self, hand):
        self.hand = hand

    def start_match(self, msg):
        self.seat = msg["your_seat"]
        self.num_players = msg["num_players"]
        self.stack = msg["starting_stack"]
        self.blind_schedule = msg["blind_schedule"]
        self.sb = self.blind_schedule[0]["small_blind"]
        self.bb = self.blind_schedule[0]["big_blind"]
        self.num_hands = msg["num_hands"]
        self.time_bank = msg["time_bank_ms"]
        self.other_bots = msg["bot_names"]

    def read_hand(self, hero, board):
        """(equity, ppot, npot) vs one random hand, from a single simulation.

        Potential only exists with cards to come, so it is 0 preflop and on the river.
        """
        if len(board) == 5:
            return equity_exact(hero, board), 0.0, 0.0
        if len(board) == 0:
            return equity_monte_carlo(hero, board, N_MAX, self.rng, target_se=TARGET_SE)[0], 0.0, 0.0
        equity, _, ppot, npot = equity_monte_carlo(hero, board, N_MAX, self.rng, potential=True, target_se=TARGET_SE)
        return equity, ppot or 0.0, npot or 0.0

    def decide(self, msg) -> dict:
        """Phase 1 to 2 policy: equity vs one random hand against pot odds, shaded by hand potential.

        free to act: raise with strong equity, else check
        facing a bet: fold below the pot-odds threshold, raise when very strong, else call
        """
        legal = msg["legal_actions"]
        hero = parse_cards(" ".join(self.hand))
        board = parse_cards(" ".join(msg["board"]))
        equity, ppot, npot = self.read_hand(hero, board)

        action, raise_to = calc_ev(msg["pot"], msg["to_call"], equity, legal, msg.get("min_raise_to"), msg.get("max_raise_to"))
        resp = {"type": "action_response", "action": action}
        if raise_to is not None:
            resp["amount"] = raise_to
        return resp
