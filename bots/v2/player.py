import random

from bots.v2.combinatorics import parse_cards
from bots.v2.equity import equity_exact, equity_monte_carlo

RAISE_EQUITY = 0.70   # raise or bet at or above this equity
BET_FRACTION = 0.75   # raise size as a fraction of the pot
IMPLIED = 0.30        # call price is cut by IMPLIED * ppot: a draw that hits wins more later
REVERSE = 0.30        # call price is raised by REVERSE * npot: a hand that gets outdrawn loses more later
PROTECT = 0.10        # raise threshold is cut by PROTECT * npot: charge the draws while ahead
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

        to_call, pot = msg["to_call"], msg["pot"]
        if equity >= RAISE_EQUITY - PROTECT * npot and "raise" in legal:
            target = to_call + int(BET_FRACTION * (pot + to_call))
            amount = max(msg["min_raise_to"], min(msg["max_raise_to"], target))
            return {"type": "action_response", "action": "raise", "amount": amount}
        if to_call == 0:
            return {"type": "action_response", "action": "check"}
        needed = to_call / (pot + to_call) * (1 - IMPLIED * ppot + REVERSE * npot)
        return {"type": "action_response", "action": "call" if equity > needed else "fold"}
