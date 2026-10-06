"""Hand-history logger: writes the observer stream to NDJSON, one message per line.

The log is the god's-eye view: `hand_start` carries every seat's `hole_cards`,
which no bot ever sees. That's deliberate — it's ground truth for validating
opponent models (ROADMAP Phase 2). Anything that should only use what a bot
could observe must ignore that field and use `hand_result.showdown` instead.
"""

import json


class HistoryLogger:
    def __init__(self, path, extra: dict | None = None):
        self.f = open(path, "w", encoding="utf-8")
        self.extra = extra or {}

    def on_event(self, msg: dict):
        if msg["type"] == "decision":
            return  # engine-internal; the CSV export carries decision context
        if msg["type"] == "match_start" and self.extra:
            msg = {**msg, **self.extra}
        self.f.write(json.dumps(msg, separators=(",", ":")) + "\n")
        if msg["type"] == "match_end":
            self.f.close()
