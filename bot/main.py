"""Bot entry point: reads engine messages on stdin, answers action_requests on stdout.

Run from the repo root:  python -m bot.main
Placeholder policy (check, else fold) until the equity and EV phases land.
"""

import json
import sys

from bot.player import Player


def decide(state: dict) -> dict:
    """state is the parsed action_request dict. Return an action dict."""
    action = "check" if "check" in state["legal_actions"] else "fold"
    return {"type": "action_response", "action": action}


def main():
    player = Player()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        if msg["type"] == "action_request":
            print(json.dumps(decide(msg)), flush=True)
        elif msg["type"] == "hand_start":
            player.new_hand(msg["your_hole_cards"])
        elif msg["type"] == "match_start":
            player.start_match(msg)
        elif msg["type"] == "match_end":
            break


if __name__ == "__main__":
    main()
