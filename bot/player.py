

class Player:
    def __init__(self, stack: int = 0):
        pass

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

    def decide(self, msg):
        