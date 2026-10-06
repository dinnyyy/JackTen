"""Main pot / side pot construction and distribution.

Pots are built from each player's *total* contribution to the hand (antes,
blinds and all streets), including players who folded: their chips stay in the
pot, they just can't win it.

Rules implemented (TDA):
- Each contribution level forms a layer; a layer is contested by the live
  players who reached it. Adjacent layers with the same contestants merge.
- A layer only one player paid into is an uncalled bet and is returned.
- Each pot is awarded separately to its best eligible hand.
- Split pots divide evenly; odd chips go one at a time to the winners in seat
  order starting from the first seat left of the button.
"""

from dataclasses import dataclass, field


@dataclass
class Pot:
    amount: int
    eligible: list[int]
    winners: list[int] = field(default_factory=list)
    shares: dict[int, int] = field(default_factory=dict)


def build_pots(contrib: dict[int, int], live: set[int]) -> tuple[list[Pot], dict[int, int]]:
    """Return (pots, uncalled_returns)."""
    levels = sorted({c for c in contrib.values() if c > 0})
    pots: list[Pot] = []
    returns: dict[int, int] = {}
    prev = 0
    for lvl in levels:
        amount = sum(min(c, lvl) - min(c, prev) for c in contrib.values())
        payers = [s for s, c in contrib.items() if c >= lvl]
        eligible = sorted(s for s in payers if s in live)
        prev = lvl
        if len(payers) == 1:
            returns[payers[0]] = returns.get(payers[0], 0) + amount
        elif not eligible:
            # Only folded players reached this level. Can't happen under normal
            # betting, but never lose chips: fold it into the pot below.
            if pots:
                pots[-1].amount += amount
            else:
                pots.append(Pot(amount, sorted(live)))
        elif pots and pots[-1].eligible == eligible:
            pots[-1].amount += amount
        else:
            pots.append(Pot(amount, eligible))
    return pots, returns


def award(pots: list[Pot], values: dict[int, tuple], seat_order: list[int]) -> dict[int, int]:
    """Distribute pots. `values` maps live seat -> comparable hand value (None-free).

    `seat_order` lists seats starting from the first seat left of the button,
    which decides odd-chip priority. Returns seat -> total chips won.
    """
    won: dict[int, int] = {}
    rank_of = {s: i for i, s in enumerate(seat_order)}
    for pot in pots:
        if len(pot.eligible) == 1:
            pot.winners = list(pot.eligible)
        else:
            best = max(values[s] for s in pot.eligible)
            pot.winners = sorted((s for s in pot.eligible if values[s] == best),
                                 key=lambda s: rank_of[s])
        share, odd = divmod(pot.amount, len(pot.winners))
        for i, s in enumerate(pot.winners):
            pot.shares[s] = share + (1 if i < odd else 0)
            won[s] = won.get(s, 0) + pot.shares[s]
    return won
