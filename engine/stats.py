"""Per-player statistics from the observer event stream.

StatsTracker watches one match and accumulates counters per *label* (a bot's
name in the lineup), so results can be merged across matches even when seats
are shuffled. Standard HUD definitions:

- VPIP   voluntarily put chips in preflop (call or raise; posting blinds doesn't count)
- PFR    raised preflop
- 3-bet  re-raised preflop when facing exactly one raise
- AF     postflop aggression factor = (bets + raises) / calls
- WTSD   went to showdown, as % of hands where they saw the flop
- W$SD   won chips at showdown, as % of showdowns
- bb/100 net big blinds won per 100 hands, each hand normalised by its own BB
"""

import math

COUNTERS = ("hands", "vpip", "pfr", "threebet", "threebet_opp", "saw_flop", "wtsd", "wsd", "wsd_n",
            "post_aggr", "post_calls", "folds", "matches", "wins", "busts", "placement_sum",
            "bot_errors", "net_chips")


def empty() -> dict:
    d = {k: 0 for k in COUNTERS}
    d.update(bb_sum=0.0, bb_sumsq=0.0, match_net=[])
    return d


class StatsTracker:
    def __init__(self, labels: list[str]):
        self.labels = labels                     # seat -> label
        self.stats = {l: empty() for l in dict.fromkeys(labels)}
        self.series: list[list[float]] = []      # per hand: net bb per label, in self.stats order

    def _s(self, seat):
        return self.stats[self.labels[int(seat)]]

    def on_event(self, m: dict):
        t = m["type"]
        if t == "hand_start":
            self.bb = m["big_blind"]
            self.start = {int(s): v for s, v in m["stacks"].items()}
            self.live = set(self.start)
            self.pf_raises = 1                   # the big blind counts as the first bet
            self.flags = {s: set() for s in self.start}
            for s in self.start:
                self._s(s)["hands"] += 1
        elif t == "action_taken":
            s, a, st = m["seat"], m["action"], m["street"]
            f = self.flags[s]
            if a == "fold":
                self.live.discard(s)
                self._s(s)["folds"] += 1
            if st == "preflop":
                if a in ("call", "raise"):
                    f.add("vpip")
                if self.pf_raises == 2 and "3bet_opp" not in f:
                    f.add("3bet_opp")
                if a == "raise":
                    f.add("pfr")
                    if self.pf_raises == 2:
                        f.add("3bet")
                    self.pf_raises += 1
            else:
                if a == "raise":
                    self._s(s)["post_aggr"] += 1
                elif a == "call":
                    self._s(s)["post_calls"] += 1
        elif t == "street_dealt" and m["street"] == "flop":
            for s in self.live:
                self.flags[s].add("saw_flop")
        elif t == "hand_result":
            winners = {w["seat"] for w in m["winners"]}
            showdown = len(m["showdown"]) >= 2
            row = dict.fromkeys(self.stats, 0.0)
            for s, start in self.start.items():
                st = self._s(s)
                f = self.flags[s]
                net = m["stacks"][str(s)] - start
                st["net_chips"] += net
                bb = net / self.bb
                row[self.labels[s]] += bb
                st["bb_sum"] += bb
                st["bb_sumsq"] += bb * bb
                for key, flag in (("vpip", "vpip"), ("pfr", "pfr"), ("threebet", "3bet"),
                                  ("threebet_opp", "3bet_opp"), ("saw_flop", "saw_flop")):
                    st[key] += flag in f
                if showdown and s in self.live:
                    st["wtsd"] += "saw_flop" in f
                    st["wsd_n"] += 1
                    st["wsd"] += s in winners
            self.series.append([round(v, 3) for v in row.values()])
        elif t == "bot_error":
            self._s(m["seat"])["bot_errors"] += 1
        elif t == "match_end":
            for place, s in enumerate(m["rankings"], start=1):
                st = self._s(s)
                st["placement_sum"] += place
                st["wins"] += place == 1
                st["busts"] += m["final_stacks"][str(s)] == 0
            per_label = {}
            for seat, label in enumerate(self.labels):
                per_label.setdefault(label, []).append(m["final_stacks"][str(seat)])
            for label, finals in per_label.items():
                st = self.stats[label]
                st["matches"] += len(finals)
                st["match_net"].extend(finals)


def merge(into: dict, other: dict) -> dict:
    for label, s in other.items():
        d = into.setdefault(label, empty())
        for k, v in s.items():
            if isinstance(v, list):
                d[k] = d.get(k, []) + v
            else:
                d[k] = d.get(k, 0) + v
    return into


def summarise(stats: dict) -> list[dict]:
    rows = []
    for label, s in stats.items():
        n = max(s["hands"], 1)
        mean = s["bb_sum"] / n
        var = max(s["bb_sumsq"] / n - mean * mean, 0.0)
        se100 = 100 * math.sqrt(var / n)
        matches = max(s["matches"], 1)
        rows.append({
            "bot": label,
            "hands": s["hands"],
            "matches": s["matches"],
            "net_chips": s["net_chips"],
            "bb_per_100": round(100 * mean, 2),
            "bb_per_100_ci95": round(1.96 * se100, 2),
            "avg_place": round(s["placement_sum"] / matches, 2),
            "win_rate": round(100 * s["wins"] / matches, 1),
            "bust_rate": round(100 * s["busts"] / matches, 1),
            "avg_final_stack": round(sum(s["match_net"]) / matches),
            "vpip": round(100 * s["vpip"] / n, 1),
            "pfr": round(100 * s["pfr"] / n, 1),
            "threebet": round(100 * s["threebet"] / max(s["threebet_opp"], 1), 1),
            "af": round(s["post_aggr"] / s["post_calls"], 2) if s["post_calls"] else None,
            "wtsd": round(100 * s["wtsd"] / max(s["saw_flop"], 1), 1),
            "wsd": round(100 * s["wsd"] / max(s["wsd_n"], 1), 1),
            "bot_errors": s["bot_errors"],
        })
    rows.sort(key=lambda r: -r["bb_per_100"])
    return rows


COLUMNS = [("bot", "bot", 16), ("hands", "hands", 8), ("bb_per_100", "bb/100", 9),
           ("bb_per_100_ci95", "+-95%", 8), ("avg_place", "place", 6), ("win_rate", "win%", 6),
           ("bust_rate", "bust%", 6), ("vpip", "VPIP", 6), ("pfr", "PFR", 6), ("threebet", "3B", 6),
           ("af", "AF", 6), ("wtsd", "WTSD", 6), ("wsd", "W$SD", 6), ("bot_errors", "errs", 5)]


def format_table(rows: list[dict]) -> str:
    def cell(v, w):
        s = "-" if v is None else str(v)
        return s[:w].rjust(w)
    head = " ".join(name.rjust(w) if k != "bot" else name.ljust(w) for k, name, w in COLUMNS)
    lines = [head, "-" * len(head)]
    for r in rows:
        lines.append(" ".join(str(r[k])[:w].ljust(w) if k == "bot" else cell(r[k], w)
                              for k, _, w in COLUMNS))
    return "\n".join(lines)
