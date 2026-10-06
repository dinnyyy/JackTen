"""One hand of No-Limit Hold'em as a state machine.

Usage:
    hand = Hand(...)
    events = hand.start()                  # posts, deals, maybe runs out
    while not hand.done:
        req = hand.request(hand.to_act)    # protocol action_request (minus timing)
        events = hand.apply(hand.to_act, action, amount)
    hand.result                            # protocol hand_result

Betting rules (TDA-consistent):
- Heads-up: the button posts the small blind, acts first preflop, last postflop.
- A big blind all-in for less than a full blind does not lower the amount to call.
- Minimum raise = size of the last *full* bet/raise on the street (at least the BB).
- An all-in for less than a full raise does not reopen betting for players who
  already acted, unless the short all-ins add up to a full raise by the time
  action returns to them.
- No raising when every other live player is all-in.
- Antes are dead money (count toward the pot, not toward the street bet).
"""

from dataclasses import dataclass, field

from engine.cards import Deck, cards_str
from engine.evaluator import evaluate, describe
from engine.pots import build_pots, award

STREETS = ["preflop", "flop", "turn", "river"]


@dataclass
class PlayerState:
    seat: int
    stack: int
    hole: list[int] = field(default_factory=list)
    street_bet: int = 0        # chips put in on the current street (excl. ante)
    total: int = 0             # chips put in this hand (incl. ante)
    folded: bool = False
    all_in: bool = False
    acted_at: int | None = None  # current bet level when this player last acted this street

    def put(self, amount: int) -> int:
        amount = min(amount, self.stack)
        self.stack -= amount
        self.street_bet += amount
        self.total += amount
        if self.stack == 0:
            self.all_in = True
        return amount


class Hand:
    def __init__(self, hand_number: int, stacks: dict[int, int], button: int,
                 small_blind: int, big_blind: int, ante: int, rng):
        if len(stacks) < 2:
            raise ValueError("need at least 2 players with chips")
        if button not in stacks:
            raise ValueError("button must be an active seat")
        self.hand_number = hand_number
        self.seats = sorted(stacks)
        self.players = {s: PlayerState(s, stacks[s]) for s in self.seats}
        self.start_stacks = dict(stacks)
        self.button = button
        self.sb, self.bb, self.ante = small_blind, big_blind, ante
        self.deck = Deck(rng)

        self.street = "preflop"
        self.board: list[int] = []
        self.history: list[dict] = []
        self.posts: list[dict] = []
        self.current_bet = 0
        self.min_raise = big_blind
        self.last_aggressor: int | None = None
        self.pending: list[int] = []
        self.to_act: int | None = None
        self.done = False
        self.result: dict | None = None
        self.sb_seat = self.bb_seat = None

    # ---------- seat helpers ----------

    def order_after(self, seat: int) -> list[int]:
        """All hand seats starting with the one left of `seat`, ending with `seat`."""
        i = self.seats.index(seat)
        return self.seats[i + 1:] + self.seats[:i + 1]

    def live(self) -> list[int]:
        return [s for s in self.seats if not self.players[s].folded]

    def able(self) -> list[int]:
        return [s for s in self.live() if not self.players[s].all_in]

    @property
    def pot(self) -> int:
        return sum(p.total for p in self.players.values())

    # ---------- start ----------

    def start(self) -> list[dict]:
        order = self.order_after(self.button)
        if self.ante:
            for s in order:
                p = self.players[s]
                amt = min(self.ante, p.stack)
                p.stack -= amt
                p.total += amt
                if p.stack == 0:
                    p.all_in = True
                self.posts.append({"seat": s, "type": "ante", "amount": amt})

        if len(self.seats) == 2:
            self.sb_seat = self.button
            self.bb_seat = self.order_after(self.button)[0]
        else:
            self.sb_seat = order[0]
            self.bb_seat = order[1]
        for seat, blind, kind in ((self.sb_seat, self.sb, "small_blind"),
                                  (self.bb_seat, self.bb, "big_blind")):
            amt = self.players[seat].put(blind)
            self.posts.append({"seat": seat, "type": kind, "amount": amt})

        self.current_bet = self.bb
        self.min_raise = self.bb

        for _ in range(2):
            for s in order:
                self.players[s].hole += self.deck.deal(1)

        self.pending = [s for s in self.order_after(self.bb_seat) if s in self.able()]
        return self._advance()

    # ---------- queries ----------

    def legal(self, seat: int) -> dict:
        p = self.players[seat]
        owe = self.current_bet - p.street_bet
        max_to = p.street_bet + p.stack
        reopened = p.acted_at is None or self.current_bet - p.acted_at >= self.min_raise
        others_can_act = any(s != seat for s in self.able())
        can_raise = max_to > self.current_bet and reopened and others_can_act
        actions = ["check"] if owe <= 0 else ["fold", "call"]
        if can_raise:
            actions.append("raise")
        return {
            "to_call": max(0, min(owe, p.stack)),
            "min_raise_to": min(self.current_bet + self.min_raise, max_to) if can_raise else 0,
            "max_raise_to": max_to if can_raise else 0,
            "legal_actions": actions,
        }

    def request(self, seat: int) -> dict:
        p = self.players[seat]
        return {
            "type": "action_request",
            "hand_number": self.hand_number,
            "street": self.street,
            "board": cards_str(self.board),
            "pot": self.pot,
            **self.legal(seat),
            "your_stack": p.stack,
            "your_bet": p.street_bet,
            "action_history": [dict(a) for a in self.history],
        }

    # ---------- actions ----------

    def normalize(self, seat: int, action: str, amount=None) -> tuple[str, int | None, str | None]:
        """Map any response onto a legal action. Returns (action, amount, correction_note)."""
        lg = self.legal(seat)
        legal = lg["legal_actions"]
        a = str(action or "").lower().strip()
        note = None
        if a == "bet":
            a = "raise"
        if a in ("allin", "all_in", "all-in", "shove"):
            if "raise" in legal:
                a, amount = "raise", lg["max_raise_to"]
            else:
                a = "call" if "call" in legal else "check"
        if a == "fold" and "check" in legal:
            return "check", None, "fold with nothing to call -> check"
        if a == "call" and "check" in legal:
            return "check", None, None
        if a == "check" and "check" not in legal:
            return "fold", None, "check facing a bet -> fold"
        if a == "raise" and "raise" not in legal:
            return ("call" if "call" in legal else "check"), None, "raise not legal -> call/check"
        if a == "raise":
            try:
                amt = int(amount)
            except (TypeError, ValueError):
                amt = lg["min_raise_to"]
                note = "raise without amount -> min raise"
            if amt < lg["min_raise_to"] or amt > lg["max_raise_to"]:
                clamped = max(lg["min_raise_to"], min(amt, lg["max_raise_to"]))
                note = f"raise to {amt} clamped to {clamped}"
                amt = clamped
            return "raise", amt, note
        if a in legal:
            return a, None, None
        return ("check" if "check" in legal else "fold"), None, f"unknown action {action!r}"

    def apply(self, seat: int, action: str, amount=None) -> list[dict]:
        if self.done or seat != self.to_act:
            raise RuntimeError(f"seat {seat} is not to act")
        action, amount, note = self.normalize(seat, action, amount)
        p = self.players[seat]

        if action == "fold":
            p.folded = True
        elif action == "check":
            p.acted_at = self.current_bet
        elif action == "call":
            p.put(self.current_bet - p.street_bet)
            p.acted_at = self.current_bet
        elif action == "raise":
            p.put(amount - p.street_bet)
            increment = amount - self.current_bet
            if increment >= self.min_raise:
                self.min_raise = increment  # full raise; short all-ins don't change it
            self.current_bet = amount
            p.acted_at = amount
            self.last_aggressor = seat
            self.pending = [s for s in self.order_after(seat) if s != seat and s in self.able()]

        if seat in self.pending:
            self.pending.remove(seat)

        rec = {"seat": seat, "action": action, "street": self.street}
        if action in ("call", "raise"):
            rec["amount"] = p.street_bet
        rec["all_in"] = p.all_in and action in ("call", "raise")
        self.history.append(rec)
        event = {"type": "action_taken", **rec, "pot": self.pot}
        if note:
            event["corrected"] = note
        return [event] + self._advance()

    # ---------- flow ----------

    def _advance(self) -> list[dict]:
        events = []
        while True:
            live = self.live()
            if len(live) == 1:
                self._finish(showdown=False)
                return events
            able = self.able()
            self.pending = [s for s in self.pending if s in able]
            if (len(able) == 1 and self.pending
                    and self.players[self.pending[0]].street_bet >= self.current_bet):
                self.pending = []  # nobody left to bet against
            if self.pending:
                self.to_act = self.pending[0]
                return events
            if self.street == "river":
                self._finish(showdown=True)
                return events
            events.append(self._next_street())

    def _next_street(self) -> dict:
        self.street = STREETS[STREETS.index(self.street) + 1]
        self.deck.deal(1)  # burn
        self.board += self.deck.deal(3 if self.street == "flop" else 1)
        for p in self.players.values():
            p.street_bet = 0
            p.acted_at = None
        self.current_bet = 0
        self.min_raise = self.bb
        self.last_aggressor = None
        able = self.able()
        self.pending = [s for s in self.order_after(self.button) if s in able] if len(able) >= 2 else []
        return {"type": "street_dealt", "street": self.street,
                "board": cards_str(self.board), "pot": self.pot}

    def _finish(self, showdown: bool):
        self.to_act = None
        self.pending = []
        self.done = True
        live = self.live()
        contrib = {s: p.total for s, p in self.players.items()}
        pots, returns = build_pots(contrib, set(live))
        left_of_button = self.order_after(self.button)

        shown: dict[int, tuple] = {}
        show_entries = []
        if showdown:
            values = {s: evaluate(self.players[s].hole + self.board) for s in live}
            won = award(pots, values, left_of_button)
            shown = self._who_shows(live, pots, values)
            order = self._showdown_order(live)
            for s in order:
                if s in shown:
                    show_entries.append({"seat": s, "hole_cards": cards_str(self.players[s].hole),
                                         "hand_rank": describe(values[s])})
                else:
                    show_entries.append({"seat": s, "hole_cards": None})
        else:
            won = award(pots, {}, left_of_button)  # single eligible player per pot

        for s, amt in returns.items():
            self.players[s].stack += amt
        for s, amt in won.items():
            self.players[s].stack += amt

        self.result = {
            "type": "hand_result",
            "hand_number": self.hand_number,
            "board": cards_str(self.board),
            "showdown": show_entries,
            "winners": [{"seat": s, "amount": won[s]} for s in sorted(won)],
            "stacks": {str(s): p.stack for s, p in self.players.items()},
            "pots": [{"amount": pt.amount, "eligible": pt.eligible,
                      "winners": pt.winners, "shares": {str(k): v for k, v in pt.shares.items()}}
                     for pt in pots],
            "uncalled_returned": {str(s): a for s, a in returns.items()},
        }

    def _showdown_order(self, live: list[int]) -> list[int]:
        """Last river aggressor shows first; otherwise first live seat left of the button."""
        order = [s for s in self.order_after(self.button) if s in live]
        if self.last_aggressor in live:
            i = order.index(self.last_aggressor)
            order = order[i:] + order[:i]
        return order

    def _who_shows(self, live, pots, values) -> set[int]:
        # All-in with action complete: every live hand is tabled (TDA).
        if any(self.players[s].all_in for s in live):
            return set(live)
        # Otherwise players show in order only if they can still win or tie a pot
        # they're eligible for; losing hands are mucked.
        shown: set[int] = set()
        for s in self._showdown_order(live):
            for pot in pots:
                if s not in pot.eligible:
                    continue
                rivals = [values[o] for o in pot.eligible if o in shown]
                if not rivals or values[s] >= max(rivals):
                    shown.add(s)
                    break
        return shown

    # ---------- views ----------

    def hole_cards(self) -> dict[str, list[str]]:
        return {str(s): cards_str(p.hole) for s, p in self.players.items()}
