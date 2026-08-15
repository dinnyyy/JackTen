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
