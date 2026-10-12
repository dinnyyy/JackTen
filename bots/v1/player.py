import random

from bots.v1.combinatorics import parse_cards
from bots.v1.equity import estimate_equity

RAISE_EQUITY = 0.70   # raise or bet at or above this equity
BET_FRACTION = 0.75   # raise size as a fraction of the pot


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

    def decide(self, msg) -> dict:
        """Phase 1 to 2 policy: equity vs one random hand against pot odds.

        free to act: raise with strong equity, else check
        facing a bet: fold below the pot-odds threshold, raise when very strong, else call
        """
        legal = msg["legal_actions"]
        hero = parse_cards(" ".join(self.hand))
        board = parse_cards(" ".join(msg["board"]))
        equity, _ = estimate_equity(hero, board, self.rng)

        to_call, pot = msg["to_call"], msg["pot"]
        if equity >= RAISE_EQUITY and "raise" in legal:
            target = to_call + int(BET_FRACTION * (pot + to_call))
            amount = max(msg["min_raise_to"], min(msg["max_raise_to"], target))
            return {"type": "action_response", "action": "raise", "amount": amount}
        if to_call == 0:
            return {"type": "action_response", "action": "check"}
        needed = to_call / (pot + to_call)
        return {"type": "action_response", "action": "call" if equity > needed else "fold"}
