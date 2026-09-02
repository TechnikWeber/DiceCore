"""
Where labelled rolls live.

The layout is meant to be readable without this code:

    datasets/
      black-d20s/
        set.json                  name, created, notes
        frames/20260901-142233-a1b2.jpg
        labels/20260901-142233-a1b2.json

One JSON per frame rather than one big index: a corrupted write costs one sample instead
of the whole set, two processes can append at once without locking, and `rsync` of half a
set is still a valid set. A dataset that takes an evening of rolling to produce should be
hard to lose.

Storage is stdlib-only so a Pi that cannot recognise anything can still *collect*.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..dice import Box, Die, RollResult, is_valid

SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    slug = SLUG_RE.sub("-", name.strip().lower()).strip("-")
    return slug or "set"


def new_id() -> str:
    """Sortable and unique: the timestamp makes a directory listing chronological."""
    return f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}"


@dataclass
class SampleDie:
    kind: str
    value: int
    box: Box
    #: False while it is only the engine's guess. Only confirmed dice are trained on —
    #: training on your own predictions is how a model learns its own mistakes by heart.
    confirmed: bool = False
    #: What the engine said, kept even after a correction. This is the honest measure of
    #: how the engine is doing, and it is free to record.
    predicted: int | None = None
    predicted_kind: str | None = None

    def to_die(self) -> Die:
        return Die(self.kind, self.value, self.box, 1.0 if self.confirmed else 0.0)


@dataclass
class Sample:
    id: str
    dice: list[SampleDie] = field(default_factory=list)
    at: float = field(default_factory=time.time)
    source: str = ""
    engine: str = ""
    note: str = ""

    @property
    def confirmed(self) -> bool:
        return bool(self.dice) and all(d.confirmed for d in self.dice)

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Sample:
        dice = []
        for raw in data.get("dice", []):
            box = raw.get("box") or {}
            dice.append(SampleDie(
                kind=str(raw.get("kind", "d6")),
                value=int(raw.get("value", 0)),
                box=Box(int(box.get("x", 0)), int(box.get("y", 0)),
                        int(box.get("w", 0)), int(box.get("h", 0))),
                confirmed=bool(raw.get("confirmed", False)),
                predicted=raw.get("predicted"),
                predicted_kind=raw.get("predicted_kind"),
            ))
        return cls(
            id=str(data.get("id", new_id())),
            dice=dice,
            at=float(data.get("at", 0.0)),
            source=str(data.get("source", "")),
            engine=str(data.get("engine", "")),
            note=str(data.get("note", "")),
        )


@dataclass
class DatasetSet:
    """
    One set of dice, photographed under one setup.

    Sets exist because a model trained across a translucent set and an opaque one under
    different lamps learns the average of two things and is worse at both. Rolling a fresh
    set for five minutes should be all it takes.
    """

    id: str
    name: str
    created: float = field(default_factory=time.time)
    note: str = ""

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


class DatasetStore:
    def __init__(self, root: Path, d10_style: str = "0-9") -> None:
        self.root = Path(root)
        #: How this set's ten-sided dice are printed. It decides which labels are legal:
        #: a die printed 1–10 has a face showing 10, and rejecting that label made the
        #: whole 1–10 setting useless for training.
        self.d10_style = d10_style

    # --- sets ---------------------------------------------------------------
    def create_set(self, name: str, note: str = "") -> DatasetSet:
        slug = slugify(name)
        directory = self.root / slug
        # Two sets called "d20s" must not merge silently; the second becomes d20s-2.
        counter = 2
        while directory.exists():
            directory = self.root / f"{slug}-{counter}"
            counter += 1
        (directory / "frames").mkdir(parents=True, exist_ok=True)
        (directory / "labels").mkdir(parents=True, exist_ok=True)
        record = DatasetSet(directory.name, name.strip() or directory.name, note=note)
        (directory / "set.json").write_text(json.dumps(record.to_json(), indent=2) + "\n")
        return record

    def list_sets(self) -> list[DatasetSet]:
        if not self.root.is_dir():
            return []
        out = []
        for directory in sorted(self.root.iterdir()):
            meta = directory / "set.json"
            if not meta.is_file():
                continue
            try:
                data = json.loads(meta.read_text())
            except (OSError, ValueError):
                continue
            out.append(DatasetSet(
                id=directory.name,
                name=str(data.get("name", directory.name)),
                created=float(data.get("created", 0.0)),
                note=str(data.get("note", "")),
            ))
        return out

    def set_dir(self, set_id: str) -> Path:
        directory = self.root / set_id
        if not (directory / "set.json").is_file():
            raise FileNotFoundError(f"No dataset set named {set_id!r}.")
        return directory

    def delete_set(self, set_id: str) -> None:
        import shutil

        shutil.rmtree(self.set_dir(set_id))

    # --- samples ------------------------------------------------------------
    def add_sample(self, set_id: str, jpeg: bytes, result: RollResult,
                   source: str = "", note: str = "") -> Sample:
        """
        Store a frame with the engine's guesses, unconfirmed.

        The guesses go in immediately rather than after confirmation, because that is what
        makes the label loop fast: the page opens with everything pre-filled and the user
        only touches what is wrong.
        """
        directory = self.set_dir(set_id)
        sample = Sample(
            id=new_id(),
            dice=[SampleDie(d.kind, d.value, d.box, confirmed=False,
                            predicted=None if d.unread else d.value,
                            predicted_kind=d.kind) for d in result.dice],
            source=source,
            engine=result.engine,
            note=note,
        )
        (directory / "frames" / f"{sample.id}.jpg").write_bytes(jpeg)
        self._write_label(directory, sample)
        return sample

    def _write_label(self, directory: Path, sample: Sample) -> None:
        path = directory / "labels" / f"{sample.id}.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(sample.to_json(), indent=2) + "\n")
        tmp.replace(path)

    def update_sample(self, set_id: str, sample_id: str, dice: list[dict[str, Any]],
                      note: str | None = None) -> Sample:
        """Apply the user's corrections. Everything named here counts as confirmed."""
        directory = self.set_dir(set_id)
        sample = self.get_sample(set_id, sample_id)
        by_index = {i: d for i, d in enumerate(sample.dice)}
        for i, raw in enumerate(dice):
            existing = by_index.get(i)
            if existing is None:
                continue
            kind = str(raw.get("kind", existing.kind))
            value = int(raw.get("value", existing.value))
            if not is_valid(kind, value, self.d10_style):
                raise ValueError(f"{kind}:{value} is not a die this vocabulary knows "
                                 f"(ten-sided dice here are printed {self.d10_style}).")
            existing.kind, existing.value = kind, value
            existing.confirmed = bool(raw.get("confirmed", True))
        if note is not None:
            sample.note = note
        self._write_label(directory, sample)
        return sample

    def get_sample(self, set_id: str, sample_id: str) -> Sample:
        path = self.set_dir(set_id) / "labels" / f"{sample_id}.json"
        if not path.is_file():
            raise FileNotFoundError(f"No sample {sample_id!r} in {set_id!r}.")
        return Sample.from_json(json.loads(path.read_text()))

    def frame_path(self, set_id: str, sample_id: str) -> Path:
        return self.set_dir(set_id) / "frames" / f"{sample_id}.jpg"

    def delete_sample(self, set_id: str, sample_id: str) -> None:
        directory = self.set_dir(set_id)
        (directory / "labels" / f"{sample_id}.json").unlink(missing_ok=True)
        (directory / "frames" / f"{sample_id}.jpg").unlink(missing_ok=True)

    def iter_samples(self, set_id: str) -> Iterator[Sample]:
        labels = self.set_dir(set_id) / "labels"
        for path in sorted(labels.glob("*.json")):
            try:
                yield Sample.from_json(json.loads(path.read_text()))
            except (OSError, ValueError):
                continue  # one unreadable label must not stop a training run

    # --- what the UI shows --------------------------------------------------
    def stats(self, set_id: str) -> dict[str, Any]:
        """
        Per-class counts, which is the number that actually decides whether training is
        worth starting. "You have 412 samples" is useless if 400 of them are a d20 showing
        1 — the UI shows the thin classes so the next hundred rolls are aimed at them.
        """
        per_class: dict[str, int] = {}
        frames = confirmed_frames = dice = confirmed_dice = correct = 0
        for sample in self.iter_samples(set_id):
            frames += 1
            confirmed_frames += 1 if sample.confirmed else 0
            for die in sample.dice:
                dice += 1
                if not die.confirmed:
                    continue
                confirmed_dice += 1
                key = f"{die.kind}:{die.value}"
                per_class[key] = per_class.get(key, 0) + 1
                if die.predicted == die.value and die.predicted_kind == die.kind:
                    correct += 1
        return {
            "frames": frames,
            "confirmed_frames": confirmed_frames,
            "dice": dice,
            "confirmed_dice": confirmed_dice,
            "classes": dict(sorted(per_class.items())),
            "engine_agreement": round(correct / confirmed_dice, 3) if confirmed_dice else None,
            "thin_classes": sorted(k for k, v in per_class.items() if v < 10),
        }
