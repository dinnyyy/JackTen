from treys import Card, Deck, Evaluator

class Player:
    def __init__(self, stack: int):
        pass

    def new_hand(hand):
        self.hand = hand

    def start_match(msg):
        self.seat = msg["your_seat"]
        self.num_players = msg["num_players"]
        self.stack = msg["starting_stack"]
        self.sb = msg["blind_schedule"]["small_blind"]
        self.bb = msg["blind_schedule"]["big_blind"]
        self.num_hands = msg["num_hands"]
        self.time_bank = msg["time_bank_msg"]
        self.other_bots = msg["bot_names"]