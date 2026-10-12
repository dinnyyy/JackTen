"""Bot entry point: reads engine messages on stdin, answers action_requests on stdout.

Run from the repo root:  python -m bot_v2.main
Policy lives in bot/player.py (equity and hand potential vs pot odds).
"""

import json
import sys

from bot_v2.player import Player


def safe_action(state: dict) -> dict:
    action = "check" if "check" in state["legal_actions"] else "fold"
    return {"type": "action_response", "action": action}


def decide(player: Player, state: dict) -> dict:
    """state is the parsed action_request dict. Never raises: any error means check/fold."""
    try:
        return player.decide(state)
    except Exception as e:
        print(f"decide failed: {e!r}", file=sys.stderr, flush=True)
        return safe_action(state)


def main():
    player = Player()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        if msg["type"] == "action_request":
            print(json.dumps(decide(player, msg)), flush=True)
        elif msg["type"] == "hand_start":
            player.new_hand(msg["your_hole_cards"])
        elif msg["type"] == "match_start":
            player.start_match(msg)
        elif msg["type"] == "match_end":
            break


if __name__ == "__main__":
    main()
