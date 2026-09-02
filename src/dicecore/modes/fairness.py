"""
Is this die fair?

The one thing a machine that reads dice can do that a person at a table cannot: count. Roll
the same die a few hundred times and the answer stops being a feeling.

A chi-square goodness-of-fit test against a flat distribution, with the critical values
written out rather than pulled from scipy — this needs one number from a table, not a
statistics stack on a Raspberry Pi.

Read the answer carefully: a test that does not flag a die is **not** proof the die is fair,
it is a failure to prove that it is not. And a die that is flagged once in twenty tests is
what a 5 % threshold means, not a scandal.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from ..dice import values_for

#: Upper-tail critical values of the chi-square distribution, by degrees of freedom.
#: df = faces - 1, so a d6 uses 5 and a d20 uses 19.
CRITICAL = {
    1: (3.841, 6.635), 2: (5.991, 9.210), 3: (7.815, 11.345), 4: (9.488, 13.277),
    5: (11.070, 15.086), 6: (12.592, 16.812), 7: (14.067, 18.475), 8: (15.507, 20.090),
    9: (16.919, 21.666), 10: (18.307, 23.209), 11: (19.675, 24.725), 12: (21.026, 26.217),
    13: (22.362, 27.688), 14: (23.685, 29.141), 15: (24.996, 30.578), 16: (26.296, 32.000),
    17: (27.587, 33.409), 18: (28.869, 34.805), 19: (30.144, 36.191), 20: (31.410, 37.566),
    21: (32.671, 38.932), 22: (33.924, 40.289), 23: (35.172, 41.638), 24: (36.415, 42.980),
    25: (37.652, 44.314), 26: (38.885, 45.642), 27: (40.113, 46.963), 28: (41.337, 48.278),
    29: (42.557, 49.588), 30: (43.773, 50.892),
}

#: The test wants at least this many expected rolls per face before it means anything.
#: Five is the usual rule of thumb — which is 30 throws for a d6 and 100 for a d20.
MIN_EXPECTED = 5


@dataclass
class Tally:
    """How often each face has come up, for one kind of die."""

    kind: str = "d6"
    counts: Counter[int] = field(default_factory=Counter)
    d10_style: str = "0-9"

    @property
    def rolls(self) -> int:
        return sum(self.counts.values())

    def observe(self, value: int) -> None:
        self.counts[value] += 1

    def reset(self) -> None:
        self.counts.clear()

    def faces(self) -> list[int]:
        return values_for(self.kind, self.d10_style)

    def chi_square(self) -> tuple[float, int]:
        """The statistic and its degrees of freedom."""
        faces = self.faces()
        expected = self.rolls / len(faces) if faces else 0.0
        if expected <= 0:
            return 0.0, max(0, len(faces) - 1)
        statistic = sum((self.counts.get(face, 0) - expected) ** 2 / expected for face in faces)
        return statistic, len(faces) - 1

    def verdict(self) -> dict[str, Any]:
        """
        What the numbers allow you to say — and no more than that.

        Deliberately three answers, not two: not enough data yet, nothing unusual, or
        unusual. "Fair" is not one of them, because this test cannot show that.
        """
        faces = self.faces()
        statistic, df = self.chi_square()
        needed = MIN_EXPECTED * len(faces)
        expected = self.rolls / len(faces) if faces else 0.0
        five, one = CRITICAL.get(df, (0.0, 0.0))

        if self.rolls < needed:
            state = "not enough"
            wording = (f"{self.rolls} of at least {needed} throws — a {self.kind} needs about "
                       f"{needed} before the test says anything.")
        elif statistic > one:
            state = "very unusual"
            wording = (f"χ² = {statistic:.1f} against {one} at the 1 % mark. This distribution "
                       f"would come up by chance less than once in a hundred fair dice.")
        elif statistic > five:
            state = "unusual"
            wording = (f"χ² = {statistic:.1f} against {five} at the 5 % mark. Worth another "
                       f"few hundred throws — one fair die in twenty lands here.")
        else:
            state = "nothing unusual"
            wording = (f"χ² = {statistic:.1f}, under {five}. Nothing here argues the die is "
                       f"loaded — which is not the same as showing it is fair.")

        hottest = self.counts.most_common(1)
        return {
            "kind": self.kind, "rolls": self.rolls, "faces": len(faces),
            "chi_square": round(statistic, 2), "df": df,
            "critical_5pct": five, "critical_1pct": one,
            "expected_per_face": round(expected, 1),
            "counts": {str(face): self.counts.get(face, 0) for face in faces},
            "state": state, "wording": wording, "needed": needed,
            "most_common": hottest[0][0] if hottest else None,
        }
