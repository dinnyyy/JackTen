"""Phase 0: starting-hand combinatorics and card removal.

Cards are the engine's ints 0..51 (rank = c // 4, suit = c % 4); see engine/cards.py.
A combo is a sorted pair of cards. A class is the strategic label: 'AA', 'AKs', 'AKo'.

Which function to use in equity:
    deal random board cards         -> remaining_deck(hero, board)
    enumerate opponent hands        -> live_combos(hero, board)
    opponent range with weights     -> filter_range(range, hero, board)
    read cards from a test string   -> parse_cards("As Kd")
    group hands for charts/ranges   -> combo_class, class_combos
"""

from itertools import combinations

from engine.cards import RANKS, parse_card

FULL_DECK = tuple(range(52))

# All 1,326 starting hands, each a sorted (low, high) card pair. Iterate this
# directly only when no cards are known yet; otherwise use live_combos().
ALL_COMBOS = tuple(combinations(FULL_DECK, 2))


def canonical_combo(a: int, b: int) -> tuple[int, int]:
    """Return (a, b) as a sorted pair, so (As, Kd) and (Kd, As) are the same dict key.

    Use when building a range dict {combo: weight} from cards in any order.
    Raises ValueError if both cards are the same.
    """
    if a == b:
        raise ValueError("a combo needs two different cards")
    return (a, b) if a < b else (b, a)


def combo_class(a: int, b: int) -> str:
    """Label a two-card hand by strategic class: 'QQ' (pair), 'AKs' (suited), 'AKo' (offsuit).

    Use to look up preflop ranges and charts, which are written by class, not by exact
    suits. Order of the two cards does not matter; the higher rank comes first.
    Not needed for equity itself, since AsKs and AsKd have different equity vs a board.
    """
    hi, lo = sorted((a, b), reverse=True)
    rh, rl = hi // 4, lo // 4
    if rh == rl:
        return RANKS[rh] * 2
    return RANKS[max(rh, rl)] + RANKS[min(rh, rl)] + ("s" if hi % 4 == lo % 4 else "o")


def _build_classes() -> dict[str, tuple]:
    classes: dict[str, list] = {}
    for a, b in ALL_COMBOS:
        classes.setdefault(combo_class(a, b), []).append((a, b))
    return {k: tuple(v) for k, v in classes.items()}


# 169 classes -> their combos (6 per pair, 4 per suited, 12 per offsuit).
CLASS_COMBOS = _build_classes()


def class_combos(cls: str) -> tuple:
    """All exact combos in a class: class_combos('AKs') -> the 4 suited ace-kings.

    Use to expand a range written as classes (e.g. 'QQ+, AKs') into the actual combos
    equity needs. Follow with filter_range() to remove any blocked by known cards.
    """
    return CLASS_COMBOS[cls]


def remaining_deck(*known_card_groups) -> list[int]:
    """Cards still in the deck after removing every known card (hero hand, board, ...).

    Use to deal random cards: Monte Carlo board runouts and random opponent hands
    are sampled from this list, and exact runouts are enumerated from it.
    Pass each group separately: remaining_deck(hero, board).
    """
    dead = {c for group in known_card_groups for c in group}
    return [c for c in FULL_DECK if c not in dead]


def live_combos(*known_card_groups) -> list[tuple[int, int]]:
    """Every possible opponent hand that shares no card with the known cards.

    Use as the opponent's 'random hand' list: equity vs a random hand is the average
    over these. Sizes: 1,225 with just your hole cards, 1,081 on the flop, 990 on the river.
    """
    dead = {c for group in known_card_groups for c in group}
    return [(a, b) for a, b in ALL_COMBOS if a not in dead and b not in dead]


def filter_range(range_dict: dict, *known_card_groups) -> dict:
    """Remove combos from a weighted range {combo: weight} that use a known card.

    Use whenever the opponent has a non-uniform range (Phase 4) and cards come out:
    new board cards or your own hand make some of their combos impossible. Weights of
    the surviving combos are unchanged, so renormalise afterwards if you need
    probabilities.
    """
    dead = {c for group in known_card_groups for c in group}
    return {(a, b): w for (a, b), w in range_dict.items() if a not in dead and b not in dead}


def parse_cards(s: str) -> list[int]:
    """Convert 'As Kd 7h' to card ints. Use in tests and scratch scripts; the engine
    already sends cards as strings, so this is also how to read a bot's `your_hole_cards`.
    """
    return [parse_card(c) for c in s.split()]
