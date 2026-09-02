"""
The game modes, as a table.

A mode is three decisions: which dice may appear, how the faces become a result, and what
the display says. Keeping it as data is the whole point — the next game somebody wants is an
entry here plus a function in `scoring.py`, not a change to the reader, the API or the UI.

Naming the expected dice is not decoration. Telling the engine that only d6 can appear is
the cheapest accuracy win available, and it lets a mode say "this is two dice and there are
three on the tray" instead of quietly scoring the wrong thing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..play.turns import TurnRules

ALL_KINDS = ("d4", "d6", "d8", "d10", "d100", "d12", "d20")


@dataclass(frozen=True)
class GameMode:
    id: str
    label: str
    #: One line, shown under the picker. Say what the mode *does*, not what game it is from.
    blurb: str
    #: Which kinds may appear. Narrow is better.
    kinds: tuple[str, ...]
    #: Which function in `scoring.py` reads the faces.
    rule: str
    #: How many dice this mode expects, as text for the UI ("2", "5", "1–6", "any").
    dice: str = "any"
    #: Parameters the rule takes; every one of them is editable in the UI.
    defaults: dict[str, Any] = field(default_factory=dict)
    #: True when the mode needs to remember something between throws.
    stateful: bool = False
    #: What a turn looks like. Most games are one throw and done; Kniffel is three with
    #: dice kept in between, which is what the turn machine exists for.
    turns: TurnRules = field(default_factory=TurnRules)


MODES: tuple[GameMode, ...] = (
    GameMode(
        "normal", "Normal — pips",
        "Ordinary six-sided dice, added up. Almost every board game there is.",
        ("d6",), "sum", "1–6",
    ),
    GameMode(
        "normal_extended", "Normal, extended",
        "Six-sided dice and ten-sided ones together, added up.",
        ("d6", "d10"), "sum", "1–6",
    ),
    GameMode(
        "rpg", "Tabletop roleplaying",
        "The polyhedral set: every die reported and added, percentile read as 1–100, and a "
        "natural 20 or a natural 1 called out.",
        ALL_KINDS, "rpg", "1–8",
    ),
    GameMode(
        "pool", "Dice pool — count successes",
        "Count how many dice reached the target. Warhammer, Shadowrun, World of Darkness, "
        "Blades in the Dark and a great many board games, with one threshold.",
        ("d6", "d10"), "pool", "any",
        {"threshold": 4, "double_on_max": False},
    ),
    GameMode(
        "best", "Best or worst of several",
        "Only the highest die counts — or the lowest. Advantage and disadvantage, and the "
        "way a dozen other games settle a contest.",
        ALL_KINDS, "best", "2–4",
        {"take": "high"},
    ),
    GameMode(
        "exploding", "Exploding dice",
        "A die showing its maximum is thrown again and added. The result stays open until "
        "one lands short.",
        ("d4", "d6", "d8", "d10", "d12", "d20"), "exploding", "1–3",
        stateful=True,
    ),
    GameMode(
        "under", "Roll under a target",
        "Success when the roll comes in at or under a target. Percentile for Call of "
        "Cthulhu, three six-siders for GURPS.",
        ("d100", "d10", "d6"), "under", "1–3",
        {"target": 50, "percentile": True},
    ),
    GameMode(
        "yahtzee", "Kniffel / Yahtzee",
        "Five dice, read as a combination rather than a sum: full house, straights, Kniffel. "
        "Three throws a turn, keeping what you like in between, and a scorecard in the "
        "browser.",
        ("d6",), "yahtzee", "5",
        {"rolls": 3, "chips": 0},
        turns=TurnRules(rolls=3, holds=True, chips=0, auto_end=False),
    ),
    GameMode(
        "farkle", "Farkle / Zehntausend",
        "Six dice scored on the common house rules — ones and fives, triples and straights.",
        ("d6",), "farkle", "1–6",
        {"rolls": 3, "chips": 0},
        turns=TurnRules(rolls=3, holds=True, chips=0, auto_end=False),
    ),
    GameMode(
        "backgammon", "Backgammon",
        "Two dice, and a double is four moves rather than two.",
        ("d6",), "backgammon", "2",
    ),
    GameMode(
        "maexchen", "Mäxchen",
        "Two dice as a two-digit number, higher first. 21 is the Mäxchen.",
        ("d6",), "maexchen", "2",
    ),
    GameMode(
        "counting", "One die, big",
        "A single die and nothing else, as large as the screen allows. For learning to count "
        "pips, and for a display that only has to say one number.",
        ALL_KINDS, "single", "1",
    ),
    GameMode(
        "fairness", "Fairness test",
        "Throw the same die a few hundred times and see whether the distribution argues it "
        "is loaded. The one thing only a machine that counts can do.",
        ALL_KINDS, "fairness", "1", stateful=True,
    ),
    GameMode(
        "custom", "Build your own",
        "Pick the rule and the numbers yourself: add up, count successes, take the best, or "
        "roll under. This is the mode for a game that is not in the list.",
        ALL_KINDS, "sum", "any",
        {"rule": "sum", "threshold": 4, "take": "high", "target": 50,
         "double_on_max": False, "percentile": False, "zero_is_ten": False},
    ),
)

BY_ID = {mode.id: mode for mode in MODES}
DEFAULT = "normal"


def mode_by_id(mode_id: str) -> GameMode | None:
    return BY_ID.get(mode_id)


def rules_for(mode: GameMode, overrides: dict[str, Any] | None = None) -> TurnRules:
    """
    A mode's turn rules with the table's own numbers on top.

    Chips are a house rule — some tables give three, some none — so they are a setting
    rather than part of the game's definition.
    """
    values = overrides or {}
    return TurnRules(
        rolls=max(1, int(values.get("rolls", mode.turns.rolls))),
        holds=mode.turns.holds,
        chips=max(0, min(3, int(values.get("chips", mode.turns.chips)))),
        auto_end=mode.turns.auto_end,
    )
