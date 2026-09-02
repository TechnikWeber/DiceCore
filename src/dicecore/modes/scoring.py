"""
How a handful of faces becomes a result.

Every rule in this file is a pure function from a list of `(kind, value)` to a number and a
sentence. No pixels, no config objects, no session state — which is what makes "is a full
house scored correctly" a question the test suite can answer, and what makes adding a game
a matter of writing one function rather than touching the reader.

Two conventions the whole file relies on:

* A die that could not be read is `die.unread`. Nothing here may score one; the caller
  filters them out and says so, because a scored guess is worse than a refusal. Note that
  this is *not* `value == 0` — a d10 printed 0–9 has a zero face.
* `face` is what the die *shows*; `worth` is what it is worth in this game. On a d10 printed
  0–9 those differ the moment a game decides the 0 means ten.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from ..dice import DIE_FACES, Die

Face = tuple[str, int]


def faces_of(dice: list[Die]) -> list[Face]:
    return [(d.kind, d.value) for d in dice]


def readable(dice: list[Die]) -> list[Die]:
    """
    Only the dice the engine actually read.

    Filtering on `value != 0` looked equivalent and was not: a d10 printed 0–9 shows a zero,
    and dropping it silently removed a legitimate die from every sum. `Die.unread` is the
    distinction, and it lives on the die rather than being re-derived here.
    """
    return [d for d in dice if not d.unread]


def worth(kind: str, value: int, zero_is_ten: bool = False) -> int:
    """
    What a face counts for.

    The one place the d10's oldest argument is settled: a die printed 0–9 shows a 0, and
    whether that 0 means nothing or means ten is a property of the *game*, not of the die.
    """
    if zero_is_ten and kind == "d10" and value == 0:
        return 10
    return value


def max_face(kind: str, d10_style: str = "0-9") -> int:
    """The highest face this kind can show, which is what "a natural maximum" means."""
    if kind == "d100":
        return 90
    if kind == "d10":
        return 9 if d10_style == "0-9" else 10
    return DIE_FACES.get(kind, 6)


# --- results ----------------------------------------------------------------------


@dataclass
class Score:
    """What a rule made of the dice."""

    #: The one thing that belongs on a display in big letters: "18", "3 hits", "Full house".
    headline: str
    #: The line under it: the individual faces, or how the headline was arrived at.
    detail: str = ""
    #: The primary number, when there is one. `None` for a rule whose answer is a word.
    value: int | None = None
    celebrate: bool = False
    lament: bool = False
    #: Anything a consumer might want that does not fit the three fields above.
    extras: dict[str, Any] = field(default_factory=dict)
    #: Things worth saying out loud: wrong number of dice, an unread die, a rule not met.
    warnings: list[str] = field(default_factory=list)


def _list(values: list[int]) -> str:
    return ", ".join(str(v) for v in values)


# --- the rules --------------------------------------------------------------------


def score_sum(dice: list[Die], zero_is_ten: bool = False) -> Score:
    """Add them up. The rule almost every board game uses."""
    values = [worth(d.kind, d.value, zero_is_ten) for d in dice]
    total = sum(values)
    return Score(headline=str(total), detail=_list(values), value=total,
                 extras={"values": values})


def score_pool(dice: list[Die], threshold: int, double_on_max: bool = False,
               d10_style: str = "0-9", zero_is_ten: bool = False) -> Score:
    """
    Count how many dice reached the target. Not one game — a whole family of them.

    Warhammer's "hits on 4+", Shadowrun's 5s and 6s, World of Darkness' 8s with tens
    counting twice, Blades in the Dark. One threshold and one flag covers all of it, which
    is why this is worth having as its own mode rather than as four.
    """
    hits = 0
    detail = []
    for die in dice:
        value = worth(die.kind, die.value, zero_is_ten)
        top = max_face(die.kind, d10_style)
        counts = 0
        if value >= threshold:
            counts = 2 if (double_on_max and die.value == top) else 1
        hits += counts
        detail.append(f"{value}{'!' if counts == 2 else '' if counts else '·'}")
    word = "success" if hits == 1 else "successes"
    # In proportion to the pool, not a fixed four: with three dice, every one succeeding is
    # the best result there is and used never to be worth a sound.
    worth_it = max(2, -(-len(dice) * 2 // 3)) if dice else 99
    return Score(
        headline=f"{hits} {word}",
        detail=" ".join(detail),
        value=hits,
        celebrate=hits >= worth_it,
        lament=hits == 0 and bool(dice),
        extras={"successes": hits, "threshold": threshold, "rolled": len(dice)},
    )


def score_best(dice: list[Die], take: str = "high", zero_is_ten: bool = False) -> Score:
    """
    Only the highest (or lowest) die counts.

    This is advantage and disadvantage, and it is also how a dozen games that never heard of
    them decide a contest. The dice that lost are still shown — the whole point of rolling
    two is seeing what you avoided.
    """
    values = [worth(d.kind, d.value, zero_is_ten) for d in dice]
    if not values:
        return Score("—", "no dice", None, warnings=["No dice on the tray."])
    chosen = max(values) if take == "high" else min(values)
    others = sorted((v for v in values), reverse=take == "high")
    return Score(
        headline=str(chosen),
        detail=f"{'highest' if take == 'high' else 'lowest'} of {_list(others)}",
        value=chosen,
        extras={"chosen": chosen, "values": values, "take": take},
    )


def score_under(dice: list[Die], target: int, zero_is_ten: bool = True,
                percentile: bool = False) -> Score:
    """
    Success when the roll comes in *at or under* a target. Call of Cthulhu, GURPS, RuneQuest.

    Percentile reads a d100 and a d10 together as 1–100, where a double zero is 100 — the
    one place in dice where two zeroes are the best possible result.
    """
    if percentile:
        rolled = percentile_value(dice)
        if rolled is None:
            return Score("—", "percentile needs a d100 and a d10", None,
                         warnings=["A percentile roll needs one d100 (tens) and one d10."])
    else:
        rolled = sum(worth(d.kind, d.value, zero_is_ten) for d in dice)
    made = rolled <= target
    return Score(
        headline=f"{rolled} — {'success' if made else 'failure'}",
        detail=f"target {target}",
        value=rolled,
        celebrate=made and rolled <= max(1, target // 5),   # a critical, in most such games
        lament=not made and rolled >= 96 if percentile else False,
        extras={"rolled": rolled, "target": target, "success": made},
    )


def percentile_value(dice: list[Die]) -> int | None:
    """d100 (tens) plus d10 (units) as 1–100; 00 and 0 is 100."""
    tens = next((d for d in dice if d.kind == "d100"), None)
    units = next((d for d in dice if d.kind == "d10"), None)
    if tens is None or units is None:
        return None
    value = tens.value + units.value
    return 100 if value == 0 else value


# --- games ------------------------------------------------------------------------

#: Yahtzee combinations, best first. Each entry is (name, test, score).
YAHTZEE_ORDER = (
    "yahtzee", "large straight", "small straight", "full house",
    "four of a kind", "three of a kind", "chance",
)


def yahtzee_combination(values: list[int]) -> tuple[str, int]:
    """
    The best combination five dice make, and what it scores.

    Scoring follows the common German Kniffel sheet: fixed points for the named
    combinations, the sum for a plain chance. Straights are checked on the *set* of values,
    because a small straight does not care that the fifth die repeated one of them.
    """
    counts = Counter(values)
    unique = set(values)
    total = sum(values)
    if 5 in counts.values():
        return "yahtzee", 50
    if unique >= {1, 2, 3, 4, 5} or unique >= {2, 3, 4, 5, 6}:
        return "large straight", 40
    if any(unique >= set(run) for run in ({1, 2, 3, 4}, {2, 3, 4, 5}, {3, 4, 5, 6})):
        return "small straight", 30
    if sorted(counts.values()) == [2, 3]:
        return "full house", 25
    if 4 in counts.values():
        return "four of a kind", total
    if 3 in counts.values():
        return "three of a kind", total
    return "chance", total


def score_yahtzee(dice: list[Die]) -> Score:
    values = sorted(d.value for d in dice)
    # The count is checked once, generically, in `modes.check_dice` — repeating it here
    # produced two sentences saying the same thing.
    if not values:
        return Score("—", "no dice", None)
    warnings: list[str] = []
    name, points = yahtzee_combination(values)
    return Score(
        headline=name.title(),
        detail=f"{_list(values)} · {points} points",
        value=points,
        celebrate=name in ("yahtzee", "large straight"),
        lament=name == "chance" and points <= 12,
        extras={"combination": name, "points": points, "values": values},
        warnings=warnings,
    )


#: Farkle single-die scores. Everything else only scores as part of a set.
FARKLE_SINGLES = {1: 100, 5: 50}


def farkle_score(values: list[int]) -> tuple[int, list[str]]:
    """
    Farkle / Zehntausend, on the common house rules.

    Six of a kind 3000, five 2000, four 1000, a straight 1500, three pairs 1500, a triple
    worth 100× its face (except three ones at 1000), and leftover 1s and 5s at 100 and 50.
    Rules vary from table to table — these are written down here so a disagreement is about
    the numbers in this function rather than about what the machine "meant".
    """
    counts = Counter(values)
    points = 0
    parts: list[str] = []

    if len(values) == 6 and set(values) == {1, 2, 3, 4, 5, 6}:
        return 1500, ["straight 1-6: 1500"]
    if len(values) == 6 and sorted(counts.values()) == [2, 2, 2]:
        return 1500, ["three pairs: 1500"]

    for face in sorted(counts, reverse=True):
        many = counts[face]
        if many >= 3:
            base = 1000 if face == 1 else face * 100
            multiplier = {3: 1, 4: 2, 5: 4, 6: 8}[min(many, 6)]
            points += base * multiplier
            parts.append(f"{many}×{face}: {base * multiplier}")
            counts[face] = 0
    for face, value in FARKLE_SINGLES.items():
        if counts.get(face):
            points += counts[face] * value
            parts.append(f"{counts[face]}×{face}: {counts[face] * value}")
    return points, parts


def score_farkle(dice: list[Die]) -> Score:
    values = sorted(d.value for d in dice)
    points, parts = farkle_score(values)
    farkle = points == 0
    return Score(
        headline="Farkle!" if farkle else str(points),
        detail=(_list(values) if farkle else " · ".join(parts)) or _list(values),
        value=points,
        celebrate=points >= 1000,
        lament=farkle,
        extras={"points": points, "parts": parts, "values": values, "farkle": farkle},
    )


def score_backgammon(dice: list[Die]) -> Score:
    """Two dice, and a double is four moves rather than two."""
    values = sorted((d.value for d in dice), reverse=True)
    if len(values) < 2:
        return Score("—", _list(values), None)
    doubled = values[0] == values[1]
    return Score(
        headline=f"double {values[0]}" if doubled else f"{values[0]}-{values[1]}",
        detail="four moves" if doubled else "two moves",
        value=sum(values),
        celebrate=doubled,
        extras={"values": values, "double": doubled,
                "moves": [values[0]] * 4 if doubled else values},
    )


def score_maexchen(dice: list[Die]) -> Score:
    """
    Two dice read as a two-digit number, higher die first. 21 is the Mäxchen and beats
    everything; doubles beat every ordinary number.
    """
    values = sorted((d.value for d in dice), reverse=True)
    if len(values) < 2:
        return Score("—", _list(values), None)
    number = values[0] * 10 + values[1]
    if number == 21:
        rank, name = 3, "Mäxchen!"
    elif values[0] == values[1]:
        rank, name = 2, f"double {values[0]}"
    else:
        rank, name = 1, str(number)
    return Score(
        headline=name,
        detail=f"{values[0]} and {values[1]}",
        value=number,
        celebrate=rank == 3,
        lament=number == 31,      # the lowest ordinary throw there is
        extras={"number": number, "rank": rank, "values": values},
    )


def score_single(dice: list[Die]) -> Score:
    """
    One die, one number, nothing else. The counting mode.

    Written for the case where the point is the number itself — learning to count pips, or a
    display in a shop window. Every roll is worth a small celebration.
    """
    if not dice:
        return Score("—", "", None)
    value = dice[0].value
    return Score(headline=str(value), detail=dice[0].kind, value=value,
                 celebrate=True, extras={"value": value})


def score_exploding(dice: list[Die], carried: int = 0, d10_style: str = "0-9") -> Score:
    """
    A die showing its maximum is thrown again and added — Savage Worlds' "acing".

    The one rule here that needs memory across throws: `carried` is what the previous throws
    already put on the table. The result stays *open* while any die is showing its top face,
    and the display says so with a trailing "…" so nobody walks away from half a roll.
    """
    values = [d.value for d in dice]
    still_open = any(d.value == max_face(d.kind, d10_style) for d in dice)
    total = carried + sum(values)
    return Score(
        headline=f"{total}…" if still_open else str(total),
        detail=(f"{carried} + {_list(values)}" if carried else _list(values))
               + (" — throw again" if still_open else ""),
        value=total,
        celebrate=still_open,
        extras={"total": total, "open": still_open, "carried": carried, "values": values},
    )


def score_rpg(dice: list[Die], d10_style: str = "0-9") -> Score:
    """
    The polyhedral set, read the way a table reads it.

    Not a rules engine — it does not know your modifier, your armour class or which of the
    dice on the tray was the damage. It reports what is there, adds it up, reads a d100 and
    a d10 together as a percentile when both are present, and calls out the two faces the
    whole table reacts to: a natural maximum and a natural 1 on a d20.
    """
    percentile = percentile_value(dice)
    twenties = [d for d in dice if d.kind == "d20"]
    crit = any(d.value == 20 for d in twenties)
    fumble = any(d.value == 1 for d in twenties)

    if percentile is not None and len(dice) == 2:
        return Score(headline=str(percentile), detail="percentile", value=percentile,
                     celebrate=percentile <= 5, lament=percentile >= 96,
                     extras={"percentile": percentile})

    values = [worth(d.kind, d.value, d10_style == "0-9" and d.kind == "d10") for d in dice]
    total = sum(values)
    groups = ", ".join(f"{d.kind[1:]}→{d.value}" for d in dice)
    headline = str(total)
    if crit and len(twenties) == 1 and len(dice) == 1:
        headline = "20 — critical!"
    elif fumble and len(twenties) == 1 and len(dice) == 1:
        headline = "1 — fumble"
    return Score(
        headline=headline,
        detail=groups,
        value=total,
        celebrate=crit,
        lament=fumble,
        extras={"total": total, "critical": crit, "fumble": fumble,
                "percentile": percentile, "by_die": [(d.kind, d.value) for d in dice]},
    )
