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


def ev_raise(pot, to_call, equity, r, opponents=1, rake=0.0):
    """EV of calling and then putting `r` more chips in. If the opponent calls, they match `r`.

    The raise only wins uncontested if all `opponents` fold, each at fold_prob, so f = fold_prob ** opponents.
    Callers come from the top of their own ranges, so equity when called filters by the per-opponent fold chance,
    and winning against k callers at once multiplies those chances. Each caller adds r to the pot we win.
    """
    f_each = fold_prob(pot, r)
    f = f_each ** opponents
    k = opponents * (1 - f_each) / (1 - f)   # expected callers given at least one calls
    # equity vs n random hands is about strength ** n, so strength is the per-opponent percentile; to win a called
    # pot we must beat all k callers, each drawn from the top (1 - f_each) of a range
    strength = equity ** (1 / opponents)
    e = equity_when_called(strength, f_each) ** k
    return f * pot * (1 - rake) + (1 - f) * (e * (pot + r * k) * (1 - rake) - (1 - e) * (to_call + r))


def calc_ev(pot, to_call, equity, legal, min_raise_to, max_raise_to, num_opponents=1, fractions=BET_FRACTIONS, rake=0.0):
    """Best action by EV against num_opponents live opponents. Returns (action, raise_to); raise_to is None unless raising.

    Assumes none of our chips are in this street yet, so chips added by a raise_to = raise_to.
    When facing a bet we never fold a hand in the top mdf of hands, so the bettor cannot bluff us for free.
    Multiway this floor is unchanged: the bettor's bluff must make all n defenders fold, so each may fold up to
    bbf ** (1/n) of hands, but equity vs n random hands is about percentile ** n, so the floor in equity terms
    is (bbf ** (1/n)) ** n = bbf again. With rake 0 it never binds (pot odds already call at lower equity).
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
            ev = ev_raise(pot, to_call, equity, raise_to - to_call, num_opponents, rake)
            if ev > best_ev:
                best, best_ev = ("raise", raise_to), ev
    return best

def position(seat, button, active_seats):
    """Postflop position from 0.0 (first to act) to 1.0 (the button, last to act).

    active_seats are the seats dealt into the hand. Action starts left of the button and the button acts last,
    which also holds heads-up.
    """
    seats = sorted(active_seats)
    order = sorted(seats, key=lambda s: (s - button - 1) % (max(seats) + 1))
    return order.index(seat) / (len(order) - 1) if len(order) > 1 else 1.0


REAL_WEIGHTS = (0.12, 0.03, 0.2, 0.1)   # position, per extra opponent, npot, ppot out of position


def realisation(position, opponents, ppot, npot):
    """Fraction of raw equity the hand is expected to realise, in [0.6, 1.0]. Raw equity assumes every hand reaches showdown.

    Out of position, against more opponents, and with a made hand that can still be outdrawn (npot) all cost
    equity. A drawing hand (ppot) loses extra only out of position, where it cannot see cards cheaply. Weights
    are hand-tuned starting values. ppot and npot are 0 preflop and on the river.
    """
    w_pos, w_opp, w_npot, w_ppot = REAL_WEIGHTS
    r = 1 - w_pos * (1 - position) - w_opp * (opponents - 1) - w_npot * npot - w_ppot * ppot * (1 - position)
    return max(0.6, min(1.0, r))
