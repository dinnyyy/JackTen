BET_FRACTIONS = (0.5, 0.75, 1.0)   # raise sizes tried, as a fraction of the pot after calling


def equity_to_call(call, pot):
    """Equity needed to break even on a call. `pot` already includes the bet being called."""
    return call / (pot + call)


def fold_prob(pot, bet):
    return 0.4


def ev_call(pot, to_call, equity):
    return equity * pot - (1 - equity) * to_call


def ev_raise(pot, to_call, equity, r):
    """EV of calling and then putting `r` more chips in. If the opponent calls, they match `r`."""
    f = fold_prob(pot, r)
    return f * pot + (1 - f) * (equity * (pot + r) - (1 - equity) * (to_call + r))


def calc_ev(pot, to_call, equity, legal, min_raise_to, max_raise_to, fractions=BET_FRACTIONS):
    """Best action by EV against one opponent. Returns (action, raise_to); raise_to is None unless raising.

    Assumes none of our chips are in this street yet, so chips added by a raise_to = raise_to.
    """
    best, best_ev = ("fold", None), 0.0
    if "check" in legal:
        best = ("check", None)
    elif "call" in legal:
        ev = ev_call(pot, to_call, equity)
        if ev > best_ev:
            best, best_ev = ("call", None), ev
    if "raise" in legal:
        for frac in fractions:
            raise_to = max(min_raise_to, min(max_raise_to, to_call + int(frac * (pot + to_call))))
            ev = ev_raise(pot, to_call, equity, raise_to - to_call)
            if ev > best_ev:
                best, best_ev = ("raise", raise_to), ev
    return best
