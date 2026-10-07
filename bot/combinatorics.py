"""Phase 0: starting-hand combinatorics and card removal.

Cards are the engine's ints 0..51 (rank = c // 4, suit = c % 4); see engine/cards.py.
A combo is a sorted pair of cards. A class is the strategic label: 'AA', 'AKs', 'AKo'.
"""

from itertools import combinations

from engine.cards import RANKS, parse_card

FULL_DECK = tuple(range(52))


def canonical_combo(a: int, b: int) -> tuple[int, int]:
    if a == b:
        raise ValueError("a combo needs two different cards")
    return (a, b) if a < b else (b, a)


ALL_COMBOS = tuple(combinations(FULL_DECK, 2))  # 1,326, each already sorted


def combo_class(a: int, b: int) -> str:
    """Strategic class of a combo: pairs 'QQ', suited 'AKs', offsuit 'AKo' (high card first)."""
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


CLASS_COMBOS = _build_classes()  # 169 classes -> their combos (6 / 4 / 12 each)


def class_combos(cls: str) -> tuple:
    return CLASS_COMBOS[cls]


def remaining_deck(*known_card_groups) -> list[int]:
    """Deck minus every card in every group (hero hand, board, other known cards)."""
    dead = {c for group in known_card_groups for c in group}
    return [c for c in FULL_DECK if c not in dead]


def live_combos(*known_card_groups) -> list[tuple[int, int]]:
    """Every combo that shares no card with the known cards."""
    dead = {c for group in known_card_groups for c in group}
    return [(a, b) for a, b in ALL_COMBOS if a not in dead and b not in dead]


def filter_range(range_dict: dict, *known_card_groups) -> dict:
    """Drop combos from a weighted range {combo: weight} that collide with known cards."""
    dead = {c for group in known_card_groups for c in group}
    return {(a, b): w for (a, b), w in range_dict.items() if a not in dead and b not in dead}


def parse_cards(s: str) -> list[int]:
    """'As Kd' -> [int, int]."""
    return [parse_card(c) for c in s.split()]
