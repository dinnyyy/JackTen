import random

from bots.v4.combinatorics import parse_cards
from bots.v4.equity import equity_exact, equity_monte_carlo
from bots.v4.exp_value import calc_ev, position, realisation

TARGET_SE = 0.01      # stop sampling once equity's standard error is this small
N_MAX = 10000         # cap on samples per decision


class Player:
    def __init__(self, stack: int = 0):
        self.rng = random.Random()
        self.hand = []
        self.seat = None
        self.num_players = 2
        self.players_left = 1
        self.hand_players = 2
        self.position = 1.0

    def new_hand(self, hand, msg=None):
        """msg is the hand_start message. Its stacks list the seats dealt in, which shrinks as players bust."""
        self.hand = hand
        active = [int(s) for s in msg["stacks"]] if msg and "stacks" in msg else None
        self.hand_players = len(active) if active else self.num_players
        self.players_left = self.hand_players - 1
        if active and self.seat in active:
            self.position = position(self.seat, msg["button_seat"], active)

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
        """(equity, ppot, npot) vs players_left random hands, from a single simulation.

        Potential only exists with cards to come, so it is 0 preflop and on the river.
        """
        if len(board) == 5 and self.players_left == 1:
            return equity_exact(hero, board), 0.0, 0.0
        if len(board) == 5:
            return equity_monte_carlo(hero, board, N_MAX, self.rng, self.players_left, target_se=TARGET_SE)[0], 0.0, 0.0
        if len(board) == 0:
            return equity_monte_carlo(hero, board, N_MAX, self.rng, self.players_left, target_se=TARGET_SE)[0], 0.0, 0.0
        equity, _, ppot, npot = equity_monte_carlo(hero, board, N_MAX, self.rng, self.players_left, potential=True, target_se=TARGET_SE)
        return equity, ppot or 0.0, npot or 0.0

    def decide(self, msg) -> dict:
        """Phase 2 policy: pick fold / check / call / raise by EV, from equity vs the opponents still in the hand.

        Raise sizes and the fold probability come from exp_value.calc_ev. ppot and npot are computed but not used yet.
        """
        # action_history is cumulative for the hand, so recount the folders each time
        folded = {m["seat"] for m in msg.get("action_history", []) if m["action"] == "fold"}
        self.players_left = max(1, self.hand_players - 1 - len(folded - {self.seat}))

        legal = msg["legal_actions"]
        hero = parse_cards(" ".join(self.hand))
        board = parse_cards(" ".join(msg["board"]))
        equity, ppot, npot = self.read_hand(hero, board)
        equity = min(1.0, equity * realisation(self.position, self.players_left, ppot, npot))

        action, raise_to = calc_ev(msg["pot"], msg["to_call"], equity, legal, msg.get("min_raise_to"), msg.get("max_raise_to"), self.players_left)
        resp = {"type": "action_response", "action": action}
        if raise_to is not None:
            resp["amount"] = raise_to
        return resp
