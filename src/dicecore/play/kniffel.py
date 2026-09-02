"""
Kniffel scorecards — the standard sheet and the extended one.

The first game DiceCore plays rather than merely reads, and the reason the turn machine
exists: three throws, dice kept in between, and at the end a category to book — which is a
decision no camera can make for you.

A **sheet** is a table: which categories, in which order, and where the upper bonus sits.
Two of them here, and a third would be an entry rather than a file.

House rules vary, so the ones used are written down rather than implied. Standard: the upper
bonus is 35 at 63, a second Kniffel is not a joker and simply scores 50 in its own box, and
any box may be crossed out for nothing at any time.

> **The extended sheet is a defined house sheet, not a transcription of a boxed product.**
> Six dice, more categories, a higher bonus. If the version on your table says something
> else, the numbers live in `SHEETS` below and changing them is a one-line job.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

UPPER = ("ones", "twos", "threes", "fours", "fives", "sixes")

#: Fixed-value categories. Everything not listed scores the sum of the dice, or nothing.
FIXED = {
    "full_house": 25, "small_straight": 30, "large_straight": 40, "kniffel": 50,
    "big_full_house": 40, "three_pairs": 35, "five_of_a_kind": 60,
    "six_of_a_kind": 100, "extreme_straight": 60,
}

LABELS = {
    "ones": "Ones", "twos": "Twos", "threes": "Threes", "fours": "Fours",
    "fives": "Fives", "sixes": "Sixes",
    "three_of_a_kind": "Three of a kind", "four_of_a_kind": "Four of a kind",
    "five_of_a_kind": "Five of a kind", "six_of_a_kind": "Kniffel Extreme",
    "two_pairs": "Two pairs", "three_pairs": "Three pairs",
    "full_house": "Full house", "big_full_house": "Big full house (3+3)",
    "small_straight": "Small straight", "large_straight": "Large straight",
    "extreme_straight": "Extreme straight (1–6)",
    "kniffel": "Kniffel", "chance": "Chance",
}


@dataclass(frozen=True)
class Sheet:
    """One scorecard's layout. The difference between two Kniffel variants is this table."""

    id: str
    label: str
    dice: int
    upper: tuple[str, ...]
    lower: tuple[str, ...]
    bonus_at: int
    bonus: int
    note: str = ""

    @property
    def categories(self) -> tuple[str, ...]:
        return self.upper + self.lower


STANDARD = Sheet(
    "standard", "Kniffel", 5, UPPER,
    ("three_of_a_kind", "four_of_a_kind", "full_house", "small_straight",
     "large_straight", "kniffel", "chance"),
    bonus_at=63, bonus=35,
    note="The ordinary sheet: five dice, thirteen boxes, bonus at 63.",
)

EXTREME = Sheet(
    "extreme", "Kniffel Extreme", 6, UPPER,
    ("three_of_a_kind", "four_of_a_kind", "five_of_a_kind", "six_of_a_kind",
     "two_pairs", "three_pairs", "full_house", "big_full_house",
     "small_straight", "large_straight", "extreme_straight", "chance"),
    # Four of each face rather than three: with six dice you expect one of every face per
    # throw, so booking three of one is no longer the effort the standard bonus rewards.
    bonus_at=84, bonus=50,
    note="Six dice, sixteen boxes, bonus at 84. A defined house sheet, not a boxed product.",
)

SHEETS = {sheet.id: sheet for sheet in (STANDARD, EXTREME)}

#: Kept for the modules that only ever knew the standard card.
CATEGORIES = STANDARD.categories
LOWER = STANDARD.lower
BONUS_AT = STANDARD.bonus_at
BONUS = STANDARD.bonus


def _runs(values: set[int], length: int) -> bool:
    return any(values >= set(range(start, start + length)) for start in range(1, 8 - length))


def score_for(category: str, values: list[int]) -> int:
    """What this category is worth for these dice. Zero when it is not made."""
    counts = Counter(values)
    unique = set(values)
    total = sum(values)
    most = max(counts.values(), default=0)
    pairs = sum(1 for count in counts.values() if count >= 2)

    if category in UPPER:
        face = UPPER.index(category) + 1
        return counts[face] * face
    if category == "three_of_a_kind":
        return total if most >= 3 else 0
    if category == "four_of_a_kind":
        return total if most >= 4 else 0
    if category == "five_of_a_kind":
        return FIXED[category] if most >= 5 else 0
    if category == "six_of_a_kind":
        return FIXED[category] if most >= 6 else 0
    if category == "kniffel":
        return FIXED[category] if most >= 5 else 0
    if category == "two_pairs":
        # The two best pairs, which is what makes it worth booking rather than a fallback.
        if pairs < 2:
            return 0
        best = sorted((face for face, count in counts.items() if count >= 2), reverse=True)[:2]
        return sum(face * 2 for face in best)
    if category == "three_pairs":
        return FIXED[category] if pairs >= 3 and len(values) >= 6 else 0
    if category == "full_house":
        return FIXED[category] if _has_group(counts, 3, 2) else 0
    if category == "big_full_house":
        return FIXED[category] if _has_group(counts, 3, 3) else 0
    if category == "small_straight":
        return FIXED[category] if _runs(unique, 4) else 0
    if category == "large_straight":
        return FIXED[category] if _runs(unique, 5) else 0
    if category == "extreme_straight":
        return FIXED[category] if unique >= {1, 2, 3, 4, 5, 6} else 0
    if category == "chance":
        return total
    return 0


def _has_group(counts: Counter, first: int, second: int) -> bool:
    """A group of `first` of one face and `second` of another, from different faces."""
    for face, count in counts.items():
        if count < first:
            continue
        for other, other_count in counts.items():
            if other != face and other_count >= second:
                return True
    return False


def options_for(values: list[int], sheet: Sheet = STANDARD) -> dict[str, int]:
    """Every category on this sheet and what it would score — what the browser shows."""
    return {category: score_for(category, values) for category in sheet.categories}


@dataclass
class Card:
    """One player's card. `None` means open; a booked zero is a crossed-out box."""

    name: str = "Player"
    sheet: Sheet = STANDARD
    scores: dict[str, int | None] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.scores:
            self.scores = dict.fromkeys(self.sheet.categories)

    def open_categories(self) -> list[str]:
        return [c for c in self.sheet.categories if self.scores.get(c) is None]

    def book(self, category: str, values: list[int], cross_out: bool = False) -> int:
        if category not in self.sheet.categories:
            raise ValueError(f"{category!r} is not a category on the {self.sheet.label} card.")
        if self.scores.get(category) is not None:
            raise ValueError(f"{LABELS.get(category, category)} is already booked.")
        points = 0 if cross_out else score_for(category, values)
        self.scores[category] = points
        return points

    @property
    def upper(self) -> int:
        return sum(self.scores.get(c) or 0 for c in self.sheet.upper)

    @property
    def bonus(self) -> int:
        return self.sheet.bonus if self.upper >= self.sheet.bonus_at else 0

    @property
    def lower(self) -> int:
        return sum(self.scores.get(c) or 0 for c in self.sheet.lower)

    @property
    def total(self) -> int:
        return self.upper + self.bonus + self.lower

    @property
    def complete(self) -> bool:
        return not self.open_categories()

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name, "sheet": self.sheet.id, "scores": dict(self.scores),
            "upper": self.upper, "bonus": self.bonus, "lower": self.lower,
            "total": self.total, "complete": self.complete,
            "to_bonus": max(0, self.sheet.bonus_at - self.upper),
        }


def leader(cards: list[Card]) -> int | None:
    """Index of whoever is ahead, or None while it is a tie."""
    if not cards:
        return None
    best = max(card.total for card in cards)
    winners = [i for i, card in enumerate(cards) if card.total == best]
    return winners[0] if len(winners) == 1 else None


def sheet_json(sheet: Sheet) -> dict[str, Any]:
    """What a browser needs to draw this card without knowing the rules."""
    return {
        "id": sheet.id, "label": sheet.label, "dice": sheet.dice,
        "upper": list(sheet.upper), "lower": list(sheet.lower),
        "bonus_at": sheet.bonus_at, "bonus": sheet.bonus, "note": sheet.note,
        "labels": {c: LABELS.get(c, c) for c in sheet.categories},
    }
