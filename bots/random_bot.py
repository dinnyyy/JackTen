"""Reference NDJSON bot: reads engine messages on stdin, answers action_requests on stdout.

Copy this as the starting point for a real bot. Rules of the road:
- One JSON object per line. Flush after every write.
- Only reply to `action_request`. Everything else is informational.
- Debug output goes to stderr — anything non-JSON on stdout is ignored by the engine,
  but don't rely on that.

Run against the engine:
    python play.py --bots "cmd:python bots/random_bot.py" random
    python simulate.py --bots "rb=cmd:python bots/random_bot.py" random random
"""

import json
import random
import sys


def decide(req: dict, rng: random.Random) -> dict:
    action = rng.choice(req["legal_actions"])
    if action == "raise":
        amount = rng.randint(req["min_raise_to"], req["max_raise_to"])
        return {"type": "action_response", "action": "raise", "amount": amount}
    return {"type": "action_response", "action": action}


def main():
    rng = random.Random()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        if msg["type"] == "action_request":
            sys.stdout.write(json.dumps(decide(msg, rng)) + "\n")
            sys.stdout.flush()
        elif msg["type"] == "match_end":
            break


if __name__ == "__main__":
    main()
