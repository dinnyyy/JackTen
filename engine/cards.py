"""Cards as ints 0..51: rank = c // 4 (0 = deuce .. 12 = ace), suit = c % 4.

On the wire cards are two-char strings: rank in "23456789TJQKA", suit in "cdhs".
"""

import random

RANKS = "23456789TJQKA"
SUITS = "cdhs"

RANK_NAMES = ["two", "three", "four", "five", "six", "seven", "eight",
              "nine", "ten", "jack", "queen", "king", "ace"]
RANK_PLURALS = ["twos", "threes", "fours", "fives", "sixes", "sevens", "eights",
                "nines", "tens", "jacks", "queens", "kings", "aces"]


def card_str(c: int) -> str:
    return RANKS[c // 4] + SUITS[c % 4]


def parse_card(s: str) -> int:
    if len(s) != 2 or s[0].upper() not in RANKS or s[1].lower() not in SUITS:
        raise ValueError(f"bad card: {s!r}")
    return RANKS.index(s[0].upper()) * 4 + SUITS.index(s[1].lower())


def cards_str(cs) -> list[str]:
    return [card_str(c) for c in cs]


class Deck:
    def __init__(self, rng: random.Random):
        self.cards = list(range(52))
        rng.shuffle(self.cards)

    def deal(self, n: int = 1) -> list[int]:
        out, self.cards = self.cards[:n], self.cards[n:]
        return out
