"""A live match for the browser table, in one of two modes.

play   You sit in seat 0 behind the same Bot interface every bot uses. The
       match runs in a background thread; your act() blocks until the browser
       posts an action. Snapshots only show what seat 0 may see.
watch  Every seat is a bot. Bot cards are revealed by default, hands deal
       automatically, and the match can be paused.
"""

import queue
import random
import threading
import time

from engine.bots import Bot, make_bot, parse_spec, BUILTINS
from engine.cards import cards_str
from engine.match import Match, MatchConfig, BlindLevel


class HumanBot(Bot):
    name = "You"

    def __init__(self, session: "Session"):
        self.session = session
        self.inbox: queue.Queue = queue.Queue()

    def act(self, msg, timeout=None):
        self.session.set_request(msg)
        resp = self.inbox.get()
        self.session.set_request(None)
        return resp or {}


class Session:
    def __init__(self, mode: str, bots: list[str], stack: int, sb: int, bb: int, ante: int,
                 hands: int, speed: float, blind_up: int = 0, reveal: bool | None = None):
        if mode not in ("play", "watch"):
            raise ValueError("mode must be play or watch")
        specs = [b for b in bots if b.strip()]
        if mode == "play" and not 1 <= len(specs) <= 9:
            raise ValueError("choose 1-9 opponents")
        if mode == "watch" and not 2 <= len(specs) <= 10:
            raise ValueError("choose 2-10 bots")

        self.mode = mode
        self.human_seat = 0 if mode == "play" else None
        self.lock = threading.RLock()
        self.rev = 0
        self.log: list[dict] = []
        self.request: dict | None = None
        self.last_result: dict | None = None
        self.last_actions: dict[int, str] = {}
        self.reveal = (mode == "watch") if reveal is None else reveal
        self.speed = speed
        self.auto_next = mode == "watch"
        self.next_hand = threading.Event()
        self.unpaused = threading.Event()
        self.unpaused.set()
        self.finished: dict | None = None
        self.errors: list[str] = []
        self.start_stack = stack
        self.hands_done = 0
        self.biggest_pot = 0

        players, names = [], []
        if self.human_seat is not None:
            self.human = HumanBot(self)
            players.append(self.human)
            names.append("You")
        for raw in specs:
            label, spec = parse_spec(raw)
            players.append(make_bot(spec, random.Random()))
            i = len(names) + (0 if self.human_seat is not None else 1)
            names.append(label or (f"{spec.title()} {i}" if spec in BUILTINS else f"Bot {i}"))
        self.names = names

        schedule = [BlindLevel(0, sb, bb, ante)]
        if blind_up:
            schedule = [BlindLevel(k * blind_up, sb * 2 ** k, bb * 2 ** k, ante * 2 ** k)
                        for k in range(0, max(1, hands // blind_up + 1))]
        cfg = MatchConfig(num_hands=hands, starting_stack=stack, blind_schedule=schedule,
                          enforce_time=False)
        self.match = Match(players, cfg, names=names, observers=[self])
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    # ---------- lifecycle ----------

    def _run(self):
        try:
            self.finished = self.match.run()
        except Exception as e:  # surface engine bugs in the UI rather than dying silently
            self.errors.append(f"engine error: {type(e).__name__}: {e}")
            self.finished = {"error": str(e)}
        self.bump()

    def stop(self):
        self.match.stopped = True
        if self.human_seat is not None:
            self.human.inbox.put(None)
        self.unpaused.set()
        self.next_hand.set()

    def set_paused(self, paused: bool):
        (self.unpaused.clear if paused else self.unpaused.set)()
        self.bump()

    def bump(self):
        with self.lock:
            self.rev += 1

    def set_request(self, req):
        with self.lock:
            self.request = req
            self.rev += 1

    def say(self, text, kind="info"):
        with self.lock:
            self.log.append({"text": text, "kind": kind})
            self.log = self.log[-300:]
            self.rev += 1

    def _pace(self, seconds: float):
        """Sleep between events so the table is watchable; blocks while paused."""
        self.unpaused.wait()
        if seconds > 0:
            time.sleep(seconds)
        self.unpaused.wait()

    def _is_you(self, seat) -> bool:
        return self.human_seat is not None and seat == self.human_seat

    def _human_in_hand(self) -> bool:
        hand = self.match.hand
        h = self.human_seat
        return bool(h is not None and hand and h in hand.players and not hand.players[h].folded)

    # ---------- observer stream (runs on the match thread) ----------

    def on_event(self, m: dict):
        t = m["type"]
        n = self.names
        if t == "hand_start":
            with self.lock:
                self.last_result = None
                self.last_actions = {}
            self.say(f"Hand #{m['hand_number'] + 1} — blinds {m['small_blind']}/{m['big_blind']}"
                     + (f" ante {m['ante']}" if m["ante"] else ""), "hand")
            for p in m["posts"]:
                if p["amount"]:
                    label = {"ante": "ante", "small_blind": "small blind", "big_blind": "big blind"}[p["type"]]
                    verb = "post" if self._is_you(p["seat"]) else "posts"
                    self.say(f"{n[p['seat']]} {verb} {label} {p['amount']:,}", "post")
        elif t == "action_taken":
            s, a = m["seat"], m["action"]
            with self.lock:
                self.last_actions[s] = self._action_tag(m)
            you = self._is_you(s)
            verb = (f"{'go' if you else 'goes'} all-in ({m['amount']:,})" if m.get("all_in")
                    else f"{'raise' if you else 'raises'} to {m['amount']:,}" if a == "raise"
                    else f"{'call' if you else 'calls'} {m['amount']:,}" if a == "call"
                    else a if you else f"{a}s")
            self.say(f"{n[s]} {verb}", "action")
            if m.get("corrected") and not you:
                self.say(f"  ({n[s]}: {m['corrected']})", "warn")
            if not you:
                watching_closely = self.human_seat is None or self._human_in_hand()
                self._pace(self.speed * (1 if watching_closely else 0.4))
        elif t == "street_dealt":
            with self.lock:
                self.last_actions = {}
            self.say(f"— {m['street'].title()}: {' '.join(m['board'])}  (pot {m['pot']:,})", "street")
            self._pace(self.speed * 0.8)
        elif t == "hand_result":
            self._on_result(m)
        elif t == "bot_error":
            self.errors.append(f"{n[m['seat']]}: {m['error']}")
            self.say(f"{n[m['seat']]} error: {m['error']}", "warn")
        elif t == "match_end":
            r = m["rankings"]
            tail = f" You finished #{r.index(self.human_seat) + 1}." if self.human_seat is not None else ""
            self.say(f"Match over after {m['hands_played']} hands. Winner: {n[r[0]]}.{tail}", "hand")

    def _on_result(self, m):
        n = self.names
        with self.lock:
            self.last_result = m
            self.hands_done += 1
            self.biggest_pot = max(self.biggest_pot, sum(p["amount"] for p in m["pots"]))
        for e in m["showdown"]:
            if e["hole_cards"]:
                verb = "show" if self._is_you(e["seat"]) else "shows"
                self.say(f"{n[e['seat']]} {verb} {' '.join(e['hole_cards'])} ({e['hand_rank']})", "show")
            else:
                self.say(f"{n[e['seat']]} {'muck' if self._is_you(e['seat']) else 'mucks'}", "show")
        for i, pot in enumerate(m["pots"]):
            label = "pot" if len(m["pots"]) == 1 else ("main pot" if i == 0 else f"side pot {i}")
            split = " (split)" if len(pot["winners"]) > 1 else ""
            for s, amt in pot["shares"].items():
                verb = "win" if self._is_you(int(s)) else "wins"
                self.say(f"{n[int(s)]} {verb} {amt:,} — {label}{split}", "win")
        for s, amt in m["uncalled_returned"].items():
            self.say(f"Uncalled {amt:,} returned to {n[int(s)]}", "post")
        self.next_hand.clear()
        self.bump()
        if self.match.stopped:
            return
        human_out = self.human_seat is not None and m["stacks"][str(self.human_seat)] == 0
        if self.auto_next or human_out:
            self.next_hand.wait(timeout=max(1.2, self.speed * 3.5))
        else:
            self.next_hand.wait()
        self.unpaused.wait()

    @staticmethod
    def _action_tag(m):
        a = m["action"]
        if m.get("all_in"):
            return f"All-in {m['amount']:,}"
        if a == "raise":
            return f"Raise to {m['amount']:,}"
        return a.title()

    # ---------- snapshot ----------

    def state(self) -> dict:
        match = self.match
        H = self.human_seat
        with match.lock, self.lock:
            hand = match.hand
            result = self.last_result
            shown, winners = {}, set()
            if result:
                shown = {e["seat"]: e["hole_cards"] for e in result["showdown"] if e["hole_cards"]}
                winners = {w["seat"] for w in result["winners"]}
            players = []
            for s in match.seats:
                in_hand = hand is not None and s in hand.players
                p = hand.players[s] if in_hand else None
                cards = None
                if in_hand:
                    if self._is_you(s) or s in shown or self.reveal:
                        cards = cards_str(p.hole)
                    elif not p.folded:
                        cards = ["??", "??"]
                stack = p.stack if p else match.stacks[s]
                committed = p.total if p and not hand.done else 0
                players.append({
                    "seat": s,
                    "name": self.names[s],
                    "stack": stack,
                    "net": stack + committed - self.start_stack,
                    "bet": p.street_bet if p and not hand.done else 0,
                    "folded": bool(p and p.folded),
                    "all_in": bool(p and p.all_in and not hand.done),
                    "in_hand": in_hand,
                    "busted": not in_hand and match.stacks[s] == 0,
                    "cards": cards,
                    "shown": s in shown,
                    "winner": s in winners,
                    "last_action": self.last_actions.get(s),
                    "is_button": hand is not None and hand.button == s,
                    "is_sb": hand is not None and hand.sb_seat == s,
                    "is_bb": hand is not None and hand.bb_seat == s,
                    "to_act": hand is not None and not hand.done and hand.to_act == s,
                })
            if self.finished is not None:
                status = "match_over"
            elif self.request is not None:
                status = "your_turn"
            elif hand is not None and hand.done and result is not None:
                status = "hand_over"
            else:
                status = "running"
            bb = hand.bb if hand else match.config.blind_schedule[0].big_blind
            return {
                "rev": self.rev,
                "mode": self.mode,
                "human_seat": H,
                "status": status,
                "paused": not self.unpaused.is_set(),
                "hand_number": (hand.hand_number + 1) if hand else 0,
                "num_hands": match.config.num_hands,
                "street": hand.street if hand else None,
                "board": cards_str(hand.board) if hand else [],
                "pot": hand.pot if hand else 0,
                "blinds": [hand.sb, hand.bb, hand.ante] if hand else None,
                "players": players,
                "request": self.request,
                "result": result,
                "log": self.log[-120:],
                "reveal": self.reveal,
                "speed": self.speed,
                "auto_next": self.auto_next,
                "finished": self.finished,
                "errors": self.errors[-5:],
                "session": {
                    "hands": self.hands_done,
                    "net": players[H]["net"] if H is not None else None,
                    "bb": bb,
                    "biggest_pot": self.biggest_pot,
                },
            }
