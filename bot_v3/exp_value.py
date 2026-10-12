BET_FRACTIONS = (0.5, 0.75, 1.0)   # raise sizes tried, as a fraction of the pot after calling


def bbf(bet, pot, rake=0.0):
    """Break-even bluff frequency: how often a bet must win the pot uncontested for a pure bluff to break even.

    If the opponent folds more often than this, a bluff with no equity profits.
    """
    return bet / (pot * (1 - rake) + bet)


def mdf(bet, pot, rake=0.0):
    """Minimum defence frequency: how often to continue so the bettor's bluffs cannot profit.

    Folding more than 1 - mdf lets any bluff show a profit. Always bbf + mdf = 1.
    """
    return 1 - bbf(bet, pot, rake)


def spr(eff_stack, pot):
    """Stack-to-pot ratio: pots left to bet behind. eff_stack is the smaller of our stack and the opponent's.

    Low means one bet or two commits the stacks; high means a slower game with more implied odds.
    """
    return eff_stack / pot if pot > 0 else float("inf")


def equity_to_call(call, pot, rake=0.0):
    """Equity needed to break even on a call. `pot` already includes the bet being called.

    `rake` is the fraction of a won pot the house takes, so the pot is worth pot * (1 - rake) to the winner.
    """
    return call / (pot * (1 - rake) + call)


def fold_prob(pot, bet):
    """Opponent's chance of folding to `bet`: a neutral opponent defends at exactly mdf, so folds at bbf."""
    return bbf(bet, pot)


def equity_when_called(equity, f):
    """Our equity against the hands that stay in once the opponent has folded a fraction `f` of them.

    Assumes the opponent folds their weakest hands and that equity vs a random hand is our percentile
    rank, so we beat the part of the calling range that sits below it: (equity - f) / (1 - f).
    A bluff (equity under f) therefore wins nothing when called.
    """
    if f >= 1:
        return 0.0
    return max(0.0, (equity - f) / (1 - f))


def ev_call(pot, to_call, equity, rake=0.0):
    return equity * pot * (1 - rake) - (1 - equity) * to_call


def ev_raise(pot, to_call, equity, r, rake=0.0):
    """EV of calling and then putting `r` more chips in. If the opponent calls, they match `r`."""
    f = fold_prob(pot, r)
    e = equity_when_called(equity, f)
    return f * pot * (1 - rake) + (1 - f) * (e * (pot + r) * (1 - rake) - (1 - e) * (to_call + r))


def calc_ev(pot, to_call, equity, legal, min_raise_to, max_raise_to, fractions=BET_FRACTIONS, rake=0.0):
    """Best action by EV against one opponent. Returns (action, raise_to); raise_to is None unless raising.

    Assumes none of our chips are in this street yet, so chips added by a raise_to = raise_to.
    When facing a bet we never fold a hand in the top mdf of hands, so the bettor cannot bluff us for free.
    """
    best, best_ev = ("fold", None), 0.0
    if "check" in legal:
        best = ("check", None)
    elif "call" in legal:
        ev = ev_call(pot, to_call, equity, rake)
        if ev > best_ev:
            best, best_ev = ("call", None), ev
        elif equity >= 1 - mdf(to_call, pot - to_call, rake):
            best = ("call", None)
    if "raise" in legal:
        for frac in fractions:
            raise_to = max(min_raise_to, min(max_raise_to, to_call + int(frac * (pot + to_call))))
            ev = ev_raise(pot, to_call, equity, raise_to - to_call, rake)
            if ev > best_ev:
                best, best_ev = ("raise", raise_to), ev
    return best
