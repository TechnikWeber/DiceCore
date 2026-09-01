"""
From stored rolls to (crop, label) pairs.

Separate from the trainer because this half needs no PyTorch: a Pi can check whether its
dataset is trainable, and the tests can verify the crops without a 2 GB dependency.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..dataset.store import DatasetStore
from ..engine.model import prepare_crop

#: Fewer than this many confirmed examples of a class and the model will not learn it —
#: it will learn to avoid predicting it, which looks like the class "not working".
MIN_PER_CLASS = 10
#: Below this the whole run is pointless; the UI says so instead of training for a minute
#: and producing something worse than the classic engine.
MIN_TOTAL = 60


@dataclass
class Readiness:
    """Can this set be trained, and if not, what exactly is missing?"""

    total: int
    classes: dict[str, int]
    thin: list[str]
    ready: bool
    reasons: list[str]

    def to_json(self) -> dict[str, Any]:
        return {"total": self.total, "classes": self.classes, "thin": self.thin,
                "ready": self.ready, "reasons": self.reasons}


def readiness(store: DatasetStore, set_id: str) -> Readiness:
    counts: dict[str, int] = {}
    for sample in store.iter_samples(set_id):
        for die in sample.dice:
            if die.confirmed:
                key = f"{die.kind}:{die.value}"
                counts[key] = counts.get(key, 0) + 1
    total = sum(counts.values())
    thin = sorted(k for k, v in counts.items() if v < MIN_PER_CLASS)
    reasons = []
    if total < MIN_TOTAL:
        reasons.append(f"Only {total} confirmed dice — roll until there are at least {MIN_TOTAL}.")
    if len(counts) < 2:
        reasons.append("A model needs at least two different faces to tell apart.")
    if thin:
        reasons.append(
            f"{len(thin)} face(s) have fewer than {MIN_PER_CLASS} examples: {', '.join(thin[:8])}"
            + ("…" if len(thin) > 8 else "")
            + ". They will be unreliable — aim the next rolls at them."
        )
    # Thin classes are a warning, not a blocker: waiting for a perfectly balanced dataset
    # means never training, and an imperfect model still beats no model.
    ready = total >= MIN_TOTAL and len(counts) >= 2
    return Readiness(total, dict(sorted(counts.items())), thin, ready, reasons)


def iter_crops(store: DatasetStore, set_id: str, input_size: int, mean: float, std: float
               ) -> Iterator[tuple[Any, str]]:
    """
    Yield `(crop, "d20:14")` for every confirmed die.

    Uses `engine.model.prepare_crop`, the same function inference uses. If training and
    inference ever crop differently the model degrades quietly instead of failing — the
    worst kind of bug — so there is exactly one implementation and both sides import it.
    """
    import cv2

    for sample in store.iter_samples(set_id):
        confirmed = [d for d in sample.dice if d.confirmed]
        if not confirmed:
            continue
        path: Path = store.frame_path(set_id, sample.id)
        image = cv2.imread(str(path))
        if image is None:
            continue
        for die in confirmed:
            yield prepare_crop(image, die.box, input_size, mean, std), f"{die.kind}:{die.value}"


def build_arrays(store: DatasetStore, set_id: str, input_size: int, mean: float, std: float):
    """Everything in memory as `(X, y, classes)`. A full evening of rolling is ~50 MB."""
    import numpy as np

    crops, labels = [], []
    for crop, label in iter_crops(store, set_id, input_size, mean, std):
        crops.append(crop)
        labels.append(label)
    if not crops:
        raise ValueError("No confirmed dice in this set yet.")
    classes = sorted(set(labels))
    index = {name: i for i, name in enumerate(classes)}
    return (np.stack(crops).astype("float32"),
            np.array([index[name] for name in labels], dtype="int64"),
            classes)
