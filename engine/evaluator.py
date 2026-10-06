"""Best-5-of-N hand evaluator (N = 5..7).

evaluate() returns a tuple that compares correctly with < / == / >:
(category, tiebreak ranks...). Higher is better. Ranks are 0 (deuce) .. 12 (ace).
"""

from collections import Counter

from engine.cards import RANK_NAMES, RANK_PLURALS

HIGH_CARD, PAIR, TWO_PAIR, TRIPS, STRAIGHT, FLUSH, FULL_HOUSE, QUADS, STRAIGHT_FLUSH = range(9)


def _straight_high(ranks: set[int]) -> int | None:
    """Highest card of the best straight in a rank set, or None. Handles the wheel."""
    for high in range(12, 3, -1):
        if all(r in ranks for r in range(high - 4, high + 1)):
            return high
    if {12, 0, 1, 2, 3} <= ranks:
        return 3  # A-2-3-4-5, five high
    return None


def evaluate(cards) -> tuple:
    ranks = [c // 4 for c in cards]
    suits = [c % 4 for c in cards]

    suit_counts = Counter(suits)
    flush_suit, n = suit_counts.most_common(1)[0]
    if n >= 5:
        flush_ranks = sorted((c // 4 for c in cards if c % 4 == flush_suit), reverse=True)
        sf = _straight_high(set(flush_ranks))
        if sf is not None:
            return (STRAIGHT_FLUSH, sf)
        flush = (FLUSH, *flush_ranks[:5])
    else:
        flush = None

    counts = Counter(ranks)
    # groups sorted by (count, rank) descending, e.g. [(3, 12), (2, 5), (1, 9), ...]
    groups = sorted(((cnt, r) for r, cnt in counts.items()), reverse=True)

    if groups[0][0] == 4:
        quad = groups[0][1]
        kicker = max(r for r in counts if r != quad)
        return (QUADS, quad, kicker)

    if groups[0][0] == 3 and len(groups) > 1 and groups[1][0] >= 2:
        return (FULL_HOUSE, groups[0][1], groups[1][1])

    if flush:
        return flush

    st = _straight_high(set(ranks))
    if st is not None:
        return (STRAIGHT, st)

    if groups[0][0] == 3:
        trips = groups[0][1]
        kickers = sorted((r for r in counts if r != trips), reverse=True)[:2]
        return (TRIPS, trips, *kickers)

    if groups[0][0] == 2 and groups[1][0] == 2:
        hi, lo = groups[0][1], groups[1][1]
        kicker = max(r for r in counts if r not in (hi, lo))
        return (TWO_PAIR, hi, lo, kicker)

    if groups[0][0] == 2:
        pair = groups[0][1]
        kickers = sorted((r for r in counts if r != pair), reverse=True)[:3]
        return (PAIR, pair, *kickers)

    return (HIGH_CARD, *sorted(ranks, reverse=True)[:5])


def describe(value: tuple) -> str:
    """Human-readable name, e.g. 'full house, kings full of sevens'."""
    cat = value[0]
    if cat == STRAIGHT_FLUSH:
        return "royal flush" if value[1] == 12 else f"straight flush, {RANK_NAMES[value[1]]} high"
    if cat == QUADS:
        return f"four of a kind, {RANK_PLURALS[value[1]]}"
    if cat == FULL_HOUSE:
        return f"full house, {RANK_PLURALS[value[1]]} full of {RANK_PLURALS[value[2]]}"
    if cat == FLUSH:
        return f"flush, {RANK_NAMES[value[1]]} high"
    if cat == STRAIGHT:
        return f"straight, {RANK_NAMES[value[1]]} high"
    if cat == TRIPS:
        return f"three of a kind, {RANK_PLURALS[value[1]]}"
    if cat == TWO_PAIR:
        return f"two pair, {RANK_PLURALS[value[1]]} and {RANK_PLURALS[value[2]]}"
    if cat == PAIR:
        return f"pair of {RANK_PLURALS[value[1]]}"
    return f"high card, {RANK_NAMES[value[1]]}"
