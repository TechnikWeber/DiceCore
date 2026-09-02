"""
The Kniffel scorecard.

The first game DiceCore plays rather than merely reads, and the reason the turn machine
exists: three throws, dice kept in between, and at the end a category to book — which is a
decision no camera can make for you.

Pure. Given five values it says what every category would be worth; given a card it says
what has been booked and what the totals are. The live game is in `session.py`.

House rules that vary, fixed here so an argument is about this file rather than about what
the machine "meant": the upper bonus is 35 at 63, a second Kniffel is not a joker and simply
scores 50 in its own box, and a category may be crossed out for nothing at any time.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

UPPER = ("ones", "twos", "threes", "fours", "fives", "sixes")
LOWER = ("three_of_a_kind", "four_of_a_kind", "full_house", "small_straight",
         "large_straight", "kniffel", "chance")
CATEGORIES = UPPER + LOWER

LABELS = {
    "ones": "Ones", "twos": "Twos", "threes": "Threes", "fours": "Fours",
    "fives": "Fives", "sixes": "Sixes",
    "three_of_a_kind": "Three of a kind", "four_of_a_kind": "Four of a kind",
    "full_house": "Full house", "small_straight": "Small straight",
    "large_straight": "Large straight", "kniffel": "Kniffel", "chance": "Chance",
}

#: Points for the fixed-value categories.
FIXED = {"full_house": 25, "small_straight": 30, "large_straight": 40, "kniffel": 50}

#: The upper section pays a bonus at this total, which is three of each face.
BONUS_AT = 63
BONUS = 35


def score_for(category: str, values: list[int]) -> int:
    """What this category is worth for these five dice. Zero when it is not made."""
    counts = Counter(values)
    unique = set(values)
    total = sum(values)

    if category in UPPER:
        face = UPPER.index(category) + 1
        return counts[face] * face
    if category == "three_of_a_kind":
        return total if max(counts.values(), default=0) >= 3 else 0
    if category == "four_of_a_kind":
        return total if max(counts.values(), default=0) >= 4 else 0
    if category == "full_house":
        return FIXED[category] if sorted(counts.values()) == [2, 3] else 0
    if category == "small_straight":
        runs = ({1, 2, 3, 4}, {2, 3, 4, 5}, {3, 4, 5, 6})
        return FIXED[category] if any(unique >= run for run in runs) else 0
    if category == "large_straight":
        return FIXED[category] if unique in ({1, 2, 3, 4, 5}, {2, 3, 4, 5, 6}) else 0
    if category == "kniffel":
        return FIXED[category] if max(counts.values(), default=0) == 5 else 0
    if category == "chance":
        return total
    return 0


def options_for(values: list[int]) -> dict[str, int]:
    """Every category and what it would score — what the browser puts on the card."""
    return {category: score_for(category, values) for category in CATEGORIES}


@dataclass
class Card:
    """One player's card. `None` means open; a booked zero is a crossed-out box."""

    name: str = "Player"
    scores: dict[str, int | None] = field(
        default_factory=lambda: dict.fromkeys(CATEGORIES))

    def open_categories(self) -> list[str]:
        return [c for c in CATEGORIES if self.scores.get(c) is None]

    def book(self, category: str, values: list[int], cross_out: bool = False) -> int:
        if category not in CATEGORIES:
            raise ValueError(f"{category!r} is not a category on the card.")
        if self.scores.get(category) is not None:
            raise ValueError(f"{LABELS[category]} is already booked.")
        points = 0 if cross_out else score_for(category, values)
        self.scores[category] = points
        return points

    @property
    def upper(self) -> int:
        return sum(self.scores.get(c) or 0 for c in UPPER)

    @property
    def bonus(self) -> int:
        return BONUS if self.upper >= BONUS_AT else 0

    @property
    def lower(self) -> int:
        return sum(self.scores.get(c) or 0 for c in LOWER)

    @property
    def total(self) -> int:
        return self.upper + self.bonus + self.lower

    @property
    def complete(self) -> bool:
        return not self.open_categories()

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name, "scores": dict(self.scores),
            "upper": self.upper, "bonus": self.bonus, "lower": self.lower,
            "total": self.total, "complete": self.complete,
            "to_bonus": max(0, BONUS_AT - self.upper),
        }


def leader(cards: list[Card]) -> int | None:
    """Index of whoever is ahead, or None while it is a tie."""
    if not cards:
        return None
    best = max(card.total for card in cards)
    winners = [i for i, card in enumerate(cards) if card.total == best]
    return winners[0] if len(winners) == 1 else None
