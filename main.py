import itertools
import sys, json
from treys import Card, Deck, Evaluator
from player.py import Player

def decide(state):
    """state is the parsed action_request dict. Return an action dict."""
    if "check" in state["legal_actions"]:
        return {"type": "action_response", "action": "check"}
    if state["street"] == "preflop":
           equity_needed = state["to_call"] / (state["pot"]+state["to_call"])
    return {"type": "action_response", "action": "fold"}

FULL_DECK = Deck.GetFullDeck()   
evaluator = Evaluator()            

def canonical_combo(card_a, card_b):
    return tuple(sorted((card_a, card_b)))

def all_combos():
    return [canonical_combo(a, b) for a, b in itertools.combinations(FULL_DECK, 2)]


def combo_class(card_a, card_b):
    ra, rb = Card.get_rank_int(card_a), Card.get_rank_int(card_b)
    sa, sb = Card.get_suit_int(card_a), Card.get_suit_int(card_b)

    hi, lo = (ra, rb) if ra >= rb else (rb, ra)
    hi_char, lo_char = Card.STR_RANKS[hi], Card.STR_RANKS[lo]

    if ra == rb:
        return hi_char + lo_char                 
    return hi_char + lo_char + ('s' if sa == sb else 'o')    

def remaining_deck(*known_card_groups):
    """FULL_DECK minus every card in known_card_groups. Takes *groups, not
    a single hand+board pair, so it scales to hero hand + board + N
    opponents' worth of known/blocked cards — matters for your 3–6 handed scope."""
    ...

def filter_range(range_dict, dead_cards):
    """Strip any combo from a weighted range that shares a card with
    dead_cards. This is the blocker-collision step — skipping it is what
    silently corrupts multiway equity."""
    ...

p1 = Player()

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    msg = json.loads(line)
    if msg["type"] == "action_request":
        response = decide(msg)
        print(json.dumps(response), flush=True)
    elif msg["type"] == "hand_start":
        p1.new_hand(msg["your_hole_cards"])
    elif msg["type"]=="match_start":
        p1.start_match(msg)

