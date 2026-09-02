"""
Playing, as opposed to reading.

`turns.py` is the state machine for games where one throw is not the whole story, `kniffel.py`
is the first scorecard, and `session.py` is the live game the browser and the panel both
render. All of it sits behind the reader: DiceCore reads the tray, a mode says what the faces
mean, and a session says whose turn it is and what it counts for.
"""

from .kniffel import CATEGORIES, Card, options_for, score_for
from .session import GameSession
from .turns import DieSlot, Turn, TurnRules, apply_roll, spend_chip, start_turn

__all__ = [
    "GameSession", "Turn", "TurnRules", "DieSlot", "start_turn", "apply_roll", "spend_chip",
    "Card", "CATEGORIES", "options_for", "score_for",
]
