BET_FRACTIONS = (0.5, 0.75, 1.0)   # raise sizes tried, as a fraction of the pot after calling


def equity_to_call(call, pot, rake=0.0):
    """Equity needed to break even on a call. `pot` already includes the bet being called.

    `rake` is the fraction of a won pot the house takes, so the pot is worth pot * (1 - rake) to the winner.
    """
    return call / (pot * (1 - rake) + call)


def fold_prob(pot, bet):
    return bet / (pot + bet)


def ev_call(pot, to_call, equity, rake=0.0):
    return equity * pot * (1 - rake) - (1 - equity) * to_call


def ev_raise(pot, to_call, equity, r, rake=0.0):
    """EV of calling and then putting `r` more chips in. If the opponent calls, they match `r`."""
    f = fold_prob(pot, r)
    return f * pot * (1 - rake) + (1 - f) * (equity * (pot + r) * (1 - rake) - (1 - equity) * (to_call + r))


def calc_ev(pot, to_call, equity, legal, min_raise_to, max_raise_to, fractions=BET_FRACTIONS, rake=0.0):
    """Best action by EV against one opponent. Returns (action, raise_to); raise_to is None unless raising.

    Assumes none of our chips are in this street yet, so chips added by a raise_to = raise_to.
    """
    best, best_ev = ("fold", None), 0.0
    if "check" in legal:
        best = ("check", None)
    elif "call" in legal:
        ev = ev_call(pot, to_call, equity, rake)
        if ev > best_ev:
            best, best_ev = ("call", None), ev
    if "raise" in legal:
        for frac in fractions:
            raise_to = max(min_raise_to, min(max_raise_to, to_call + int(frac * (pot + to_call))))
            ev = ev_raise(pot, to_call, equity, raise_to - to_call, rake)
            if ev > best_ev:
                best, best_ev = ("raise", raise_to), ev
    return best

def bbf(bet, pot, rake=0.0):
    """Checks if a fold will return profits. Its an fold threshold, if an
    oponent folds more thant this, a pure bluff will profit. when equity = 0, ev_raise
    should cross zero at this fold threshold"""
    return bet / (pot * (1 - rake) + bet)

def mdf(bet, pot, rake=0.0):
    """Checks how often you should continue so someone bluffing doesnt profit.
    A bot that folds 1-mdf can be bluffed to profit by anyone"""

    return 1 - bbf(bet, pot, rake)

def spr(eff_stack, pot):
    """Checks how many pots are left to bet behind. Effective stack is smaller
    of you or opponents. So if its a low spr, then closer to someone being all in, more aggresive
    Higher spr means slower game"""

    return eff_stack / pot

