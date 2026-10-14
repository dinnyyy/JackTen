"""Match driver: seats bots, runs hands, sends protocol messages.

Each bot receives exactly what the protocol says it should see from its seat.
Observers (hand-history logger, stats tracker, UI) receive the god's-eye stream:
the same broadcasts plus every player's hole cards in `hand_start`.

Table conventions:
- Moving button: the button advances to the next seat that still has chips.
- reset_stacks (cash mode): stacks go back to the starting stack after every hand, so
  hands are independent and bb/100 is measured at a constant depth. Placements are
  meaningless in this mode.
- Players who bust on the same hand are ranked by their stack at the start of
  that hand (bigger stack finishes higher).
- Invalid, missing or late responses default to check if free, else fold.
- Deals are seeded per hand number (`seed`, hand index), so two matches with the
  same seed see the same cards on the same hand number whatever the bots do
  (duplicate deals). Only the opening button draw uses the match-level rng.
- All-in convention: send `raise` with `amount == max_raise_to`. The engine also
  accepts `"action": "allin"`, and an over-sized raise is clamped to all-in.
"""

import random
import threading
import time
from dataclasses import dataclass, field, asdict

from engine.allin import expected_wins
from engine.bots import Bot, BotError
from engine.hand import Hand


@dataclass
class BlindLevel:
    hand_start: int
    small_blind: int
    big_blind: int
    ante: int = 0


@dataclass
class MatchConfig:
    num_hands: int = 500
    starting_stack: int = 20000
    blind_schedule: list[BlindLevel] = field(default_factory=lambda: [BlindLevel(0, 50, 100, 0)])
    time_per_action_ms: int = 5000
    time_bank_ms: int = 30000
    enforce_time: bool = True
    seed: int | None = None
    reset_stacks: bool = False   # cash-game mode: every hand starts from starting_stack, nobody busts
    allin_ev: bool = False   # emit an observer-only `allin_ev` event for all-in runouts

    def blinds_for(self, hand_index: int) -> BlindLevel:
        level = self.blind_schedule[0]
        for lvl in self.blind_schedule:
            if lvl.hand_start <= hand_index:
                level = lvl
        return level


class Match:
    def __init__(self, bots: list[Bot], config: MatchConfig | None = None,
                 names: list[str] | None = None, observers=()):
        if len(bots) < 2:
            raise ValueError("need at least 2 bots")
        self.bots = bots
        self.config = config or MatchConfig()
        self.names = names or [getattr(b, "name", f"bot{i}") for i, b in enumerate(bots)]
        self.observers = list(observers)
        self.rng = random.Random(self.config.seed)
        self.seats = list(range(len(bots)))
        self.stacks = {s: self.config.starting_stack for s in self.seats}
        self.time_bank = {s: self.config.time_bank_ms for s in self.seats}
        self.bust_order: list[int] = []   # earliest bust first
        self.button: int | None = None
        self.hand: Hand | None = None
        self.hands_played = 0
        self.lock = threading.RLock()     # guards self.hand for UI snapshots
        self.stopped = False

    # ---------- messaging ----------

    def _emit(self, msg: dict, seats=None):
        for s in (self.seats if seats is None else seats):
            self.bots[s].notify(msg)
        for o in self.observers:
            o.on_event(msg)

    def _observe(self, msg: dict):
        for o in self.observers:
            o.on_event(msg)

    # ---------- run ----------

    def run(self) -> dict:
        cfg = self.config
        base = {
            "type": "match_start",
            "num_players": len(self.seats),
            "starting_stack": cfg.starting_stack,
            "blind_schedule": [asdict(l) for l in cfg.blind_schedule],
            "num_hands": cfg.num_hands,
            "time_per_action_ms": cfg.time_per_action_ms,
            "time_bank_ms": cfg.time_bank_ms,
            "bot_names": self.names,
        }
        for s in self.seats:
            self.bots[s].notify({**base, "your_seat": s})
        self._observe({**base, "your_seat": None, "seed": cfg.seed})

        try:
            for h in range(cfg.num_hands):
                if self.stopped:
                    break
                active = [s for s in self.seats if self.stacks[s] > 0]
                if len(active) < 2:
                    break
                self._play_hand(h, active)
        finally:
            end = {"type": "match_end",
                   "final_stacks": {str(s): self.stacks[s] for s in self.seats},
                   "rankings": self.rankings(),
                   "hands_played": self.hands_played}
            self._emit(end)
            for b in self.bots:
                b.close()
        return end

    def rankings(self) -> list[int]:
        alive = sorted((s for s in self.seats if self.stacks[s] > 0),
                       key=lambda s: (-self.stacks[s], s))
        return alive + list(reversed(self.bust_order))

    def _next_button(self, active: list[int]) -> int:
        if self.button is None:
            return self.rng.choice(active)
        n = len(self.seats)
        for k in range(1, n + 1):
            s = (self.button + k) % n
            if s in active:
                return s
        return active[0]

    def _play_hand(self, h: int, active: list[int]):
        lvl = self.config.blinds_for(h)
        self.button = self._next_button(active)
        start_stacks = {s: self.stacks[s] for s in active}
        with self.lock:
            deal_rng = self.rng if self.config.seed is None else random.Random(f"{self.config.seed}:{h}")
            hand = Hand(h, start_stacks, self.button, lvl.small_blind, lvl.big_blind,
                        lvl.ante, deal_rng)
            self.hand = hand
            events = hand.start()

        public = {
            "type": "hand_start",
            "hand_number": h,
            "button_seat": self.button,
            "small_blind": lvl.small_blind,
            "big_blind": lvl.big_blind,
            "ante": lvl.ante,
            "stacks": {str(s): v for s, v in start_stacks.items()},  # before antes/blinds
            "posts": hand.posts,
        }
        holes = hand.hole_cards()
        for s in active:
            self.bots[s].notify({**public, "your_hole_cards": holes[str(s)]})
        self._observe({**public, "hole_cards": holes})
        self._broadcast(events, active)

        while not hand.done and not self.stopped:
            seat = hand.to_act
            req = hand.request(seat)
            resp = self._ask(seat, req)
            # observer-only: the decision context, for CSV export / training data
            self._observe({"type": "decision", "seat": seat, "hand_number": h,
                           **{k: req[k] for k in ("street", "pot", "to_call", "min_raise_to",
                                                  "max_raise_to", "your_stack", "your_bet",
                                                  "legal_actions")},
                           "response": resp, "elapsed_ms": self._last_elapsed_ms})
            with self.lock:
                events = hand.apply(seat, resp.get("action"), resp.get("amount"))
            self._broadcast(events, active)

        if not hand.done:  # stopped mid-hand (UI quit)
            return
        self.hands_played += 1
        busted = []
        for s in active:
            self.stacks[s] = hand.players[s].stack
            if self.stacks[s] == 0 and not self.config.reset_stacks:
                busted.append(s)
        # bust together: smaller starting stack is out first
        for s in sorted(busted, key=lambda s: (start_stacks[s], -s)):
            self.bust_order.append(s)
        if self.config.allin_ev and hand.runout:
            ev = expected_wins(hand.runout, self.config.seed, h)
            won = {w["seat"]: w["amount"] for w in hand.result["winners"]}
            self._observe({"type": "allin_ev", "hand_number": h,
                           "adjust": {str(s): round(v - won.get(s, 0), 2) for s, v in ev.items()}})
        result = dict(hand.result)
        result["stacks"] = {str(s): self.stacks[s] for s in self.seats}
        self._emit(result, active)
        if self.config.reset_stacks:
            self.stacks = {s: self.config.starting_stack for s in self.seats}

    def _broadcast(self, events, seats):
        for e in events:
            self._emit(e, seats)

    def _ask(self, seat: int, req: dict) -> dict:
        cfg = self.config
        bot = self.bots[seat]
        req["time_remaining_ms"] = self.time_bank[seat]
        timeout = (cfg.time_per_action_ms + self.time_bank[seat]) / 1000 if cfg.enforce_time else None
        t0 = time.perf_counter()
        try:
            resp = bot.act(req, timeout)
            if not isinstance(resp, dict):
                raise BotError(f"response is not an object: {resp!r}")
        except Exception as e:  # never let one bot crash the match
            self._observe({"type": "bot_error", "seat": seat, "hand_number": req["hand_number"],
                           "error": f"{type(e).__name__}: {e}"})
            resp = {}
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        self._last_elapsed_ms = elapsed_ms
        if cfg.enforce_time:
            over = elapsed_ms - cfg.time_per_action_ms
            if over > 0:
                self.time_bank[seat] -= over
                if self.time_bank[seat] < 0:
                    self.time_bank[seat] = 0
                    self._observe({"type": "bot_error", "seat": seat,
                                   "hand_number": req["hand_number"], "error": "time bank exhausted"})
                    resp = {}
        return resp
