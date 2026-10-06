"""CSV export of simulation results.

During a run, each match writes its own part files via CsvExporter (an
observer); afterwards combine_parts() concatenates them into one CSV per table.
The column reference lives in docs/sim_outputs.md and in TABLES below.
"""

import csv
import glob
import os

# file -> (description, columns)
TABLES = {
    "actions": ("Every decision: the context the bot saw, what it did, and how long it took", [
        "match", "hand", "action_idx", "street", "seat", "bot", "position", "hole_cards", "board",
        "pot_before", "to_call", "stack_before", "street_bet_before", "min_raise_to", "max_raise_to",
        "legal_actions", "requested_action", "requested_amount", "action", "amount", "chips_added",
        "all_in", "corrected", "pot_after", "elapsed_ms",
    ]),
    "hands": ("One row per player per hand: cards, position, result, and HUD flags", [
        "match", "hand", "seat", "bot", "position", "num_players", "button_seat", "small_blind",
        "big_blind", "ante", "hole_cards", "board", "start_stack", "end_stack", "net_chips", "net_bb",
        "vpip", "pfr", "saw_flop", "folded_on", "went_to_showdown", "showed", "hand_rank",
        "won_chips", "uncalled_returned",
    ]),
    "pots": ("Every main and side pot: size, who could win it, who did", [
        "match", "hand", "pot_index", "amount", "eligible_seats", "eligible_bots",
        "winner_seats", "winner_bots", "split", "shares",
    ]),
    "matches": ("One row per seat per match: final stack and finishing place", [
        "match", "seed", "seat", "bot", "final_stack", "net_chips", "place", "busted", "hands_played",
    ]),
    "errors": ("Bot timeouts, crashes and invalid responses", [
        "match", "hand", "seat", "bot", "error",
    ]),
}


def positions(seats: list[int], button: int) -> dict[int, str]:
    """Seat -> position name (BTN, SB, BB, UTG, ..., LJ, HJ, CO)."""
    i = seats.index(button)
    order = seats[i + 1:] + seats[:i + 1]          # SB first, button last
    if len(order) == 2:
        return {button: "BTN", order[0]: "BB"}       # heads-up: button posts the SB
    m = len(order) - 3
    if m <= 3:
        middle = ["UTG", "HJ", "CO"][3 - m:]
    else:
        middle = ["UTG"] + [f"UTG+{k}" for k in range(1, m - 3)] + ["LJ", "HJ", "CO"]
    names = ["SB", "BB"] + middle + ["BTN"]
    return dict(zip(order, names))


class CsvExporter:
    def __init__(self, parts_dir: str, match_index: int, seed: int, labels: list[str],
                 tables=("actions", "hands", "pots", "matches", "errors")):
        self.m = match_index
        self.seed = seed
        self.labels = labels
        self.files, self.w = {}, {}
        for t in tables:
            f = open(os.path.join(parts_dir, f"{t}_{match_index:05d}.csv"), "w", newline="", encoding="utf-8")
            self.files[t] = f
            self.w[t] = csv.DictWriter(f, fieldnames=TABLES[t][1])
            self.w[t].writeheader()
        self.hand = None

    def _row(self, table, **row):
        if table in self.w:
            self.w[table].writerow(row)

    def on_event(self, m: dict):
        t = m["type"]
        if t == "hand_start":
            seats = sorted(int(s) for s in m["stacks"])
            self.hand = {
                "n": m["hand_number"], "start": {int(s): v for s, v in m["stacks"].items()},
                "holes": {int(s): " ".join(c) for s, c in m["hole_cards"].items()},
                "pos": positions(seats, m["button_seat"]), "meta": m, "board": "",
                "bet": {s: 0 for s in seats}, "pot": 0, "idx": 0,
                "flags": {s: set() for s in seats}, "folded_on": {}, "decision": None,
            }
            for p in m["posts"]:
                self.hand["pot"] += p["amount"]
                if p["type"] != "ante":
                    self.hand["bet"][p["seat"]] += p["amount"]
        elif t == "decision":
            self.hand["decision"] = m
        elif t == "action_taken":
            h = self.hand
            s, a = m["seat"], m["action"]
            d = h["decision"] or {}
            resp = d.get("response") or {}
            before = h["bet"][s]
            if a in ("call", "raise"):
                h["bet"][s] = m["amount"]
            added = h["bet"][s] - before
            if m["street"] == "preflop" and a in ("call", "raise"):
                h["flags"][s].add("vpip")
                if a == "raise":
                    h["flags"][s].add("pfr")
            if a == "fold":
                h["folded_on"][s] = m["street"]
            self._row("actions", match=self.m, hand=h["n"], action_idx=h["idx"], street=m["street"],
                      seat=s, bot=self.labels[s], position=h["pos"][s], hole_cards=h["holes"][s],
                      board=h["board"], pot_before=d.get("pot", m["pot"] - added),
                      to_call=d.get("to_call"), stack_before=d.get("your_stack"),
                      street_bet_before=d.get("your_bet", before),
                      min_raise_to=d.get("min_raise_to"), max_raise_to=d.get("max_raise_to"),
                      legal_actions="|".join(d.get("legal_actions", [])),
                      requested_action=resp.get("action"), requested_amount=resp.get("amount"),
                      action=a, amount=m.get("amount", ""), chips_added=added,
                      all_in=int(bool(m.get("all_in"))), corrected=m.get("corrected", ""),
                      pot_after=m["pot"], elapsed_ms=d.get("elapsed_ms"))
            h["idx"] += 1
            h["decision"] = None
        elif t == "street_dealt":
            h = self.hand
            h["board"] = " ".join(m["board"])
            h["bet"] = {s: 0 for s in h["bet"]}
            if m["street"] == "flop":
                for s in h["start"]:
                    if s not in h["folded_on"]:
                        h["flags"][s].add("saw_flop")
        elif t == "hand_result":
            self._hand_result(m)
        elif t == "bot_error":
            self._row("errors", match=self.m, hand=m.get("hand_number"), seat=m["seat"],
                      bot=self.labels[m["seat"]], error=m["error"])
        elif t == "match_end":
            place = {s: i + 1 for i, s in enumerate(m["rankings"])}
            for s, label in enumerate(self.labels):
                final = m["final_stacks"][str(s)]
                self._row("matches", match=self.m, seed=self.seed, seat=s, bot=label, final_stack=final,
                          net_chips=final - self.starting_stack, place=place[s],
                          busted=int(final == 0), hands_played=m["hands_played"])
            for f in self.files.values():
                f.close()
        elif t == "match_start":
            self.starting_stack = m["starting_stack"]

    def _hand_result(self, m):
        h = self.hand
        meta = h["meta"]
        L = self.labels
        shown = {e["seat"]: e for e in m["showdown"]}
        showdown = len(m["showdown"]) >= 2
        won = {w["seat"]: w["amount"] for w in m["winners"]}
        returned = {int(s): a for s, a in m.get("uncalled_returned", {}).items()}
        board = " ".join(m["board"])
        for s, start in h["start"].items():
            end = m["stacks"][str(s)]
            e = shown.get(s)
            f = h["flags"][s]
            self._row("hands", match=self.m, hand=h["n"], seat=s, bot=L[s], position=h["pos"][s],
                      num_players=len(h["start"]), button_seat=meta["button_seat"],
                      small_blind=meta["small_blind"], big_blind=meta["big_blind"], ante=meta["ante"],
                      hole_cards=h["holes"][s], board=board, start_stack=start, end_stack=end,
                      net_chips=end - start, net_bb=round((end - start) / meta["big_blind"], 3),
                      vpip=int("vpip" in f), pfr=int("pfr" in f), saw_flop=int("saw_flop" in f),
                      folded_on=h["folded_on"].get(s, ""),
                      went_to_showdown=int(showdown and e is not None),
                      showed=int(bool(e and e.get("hole_cards"))),
                      hand_rank=(e or {}).get("hand_rank", ""),
                      won_chips=won.get(s, 0), uncalled_returned=returned.get(s, 0))
        for i, p in enumerate(m.get("pots", [])):
            self._row("pots", match=self.m, hand=h["n"], pot_index=i, amount=p["amount"],
                      eligible_seats="|".join(map(str, p["eligible"])),
                      eligible_bots="|".join(L[s] for s in p["eligible"]),
                      winner_seats="|".join(map(str, p["winners"])),
                      winner_bots="|".join(L[s] for s in p["winners"]),
                      split=int(len(p["winners"]) > 1),
                      shares="|".join(f"{L[int(s)]}:{v}" for s, v in p["shares"].items()))


def combine_parts(parts_dir: str, out_dir: str) -> dict[str, int]:
    """Concatenate per-match part files into <table>.csv. Returns table -> row count."""
    counts = {}
    for table in TABLES:
        parts = sorted(glob.glob(os.path.join(parts_dir, f"{table}_*.csv")))
        if not parts:
            continue
        n = 0
        with open(os.path.join(out_dir, f"{table}.csv"), "w", newline="", encoding="utf-8") as out:
            out.write(",".join(TABLES[table][1]) + "\n")
            for p in parts:
                with open(p, encoding="utf-8") as f:
                    next(f, None)                 # skip the part's header
                    for line in f:
                        out.write(line)
                        n += 1
                os.remove(p)
        counts[table] = n
    try:
        os.rmdir(parts_dir)
    except OSError:
        pass
    return counts


def write_rows(path: str, rows: list[dict]):
    if not rows:
        return 0
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(dict.fromkeys(k for r in rows for k in r)))
        w.writeheader()
        w.writerows(rows)
    return len(rows)
