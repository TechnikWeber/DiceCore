"""
The trained engine: find the dice the cheap way, classify each one with a network.

Two stages on purpose (see docs/CONCEPT.md): segmentation is a solved problem that costs
nothing and needs no labels, while *reading* a die is the part that needs learning. Crops
are also far cheaper to label than boxes — the label UI only ever asks "what is this die?",
never "draw a rectangle" — and adding a new set of dice retrains only the classifier.

A model is a directory: `model.onnx` plus `model.json` describing what its outputs mean.
Anything else in there is ignored, so a training run can drop its own notes beside it.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import Settings
from ..dice import Die, Frame, RollResult, is_valid
from .base import Engine, EngineError
from .classic import ClassicEngine

MODEL_FILE = "model.onnx"
META_FILE = "model.json"


@dataclass
class ModelMeta:
    """What the network's outputs mean. Written by training, read by inference."""

    #: Class index → "d20:14". The order is the network's output order and must never be
    #: sorted, rebuilt or "cleaned up" on load — that silently remaps every prediction.
    classes: list[str]
    input_size: int = 64
    #: Mean/std used at training time; inference must match exactly.
    mean: float = 0.5
    std: float = 0.25
    trained_at: float = 0.0
    samples: int = 0
    accuracy: float = 0.0
    note: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "classes": self.classes, "input_size": self.input_size, "mean": self.mean,
            "std": self.std, "trained_at": self.trained_at, "samples": self.samples,
            "accuracy": self.accuracy, "note": self.note,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> ModelMeta:
        classes = data.get("classes")
        if not isinstance(classes, list) or not classes:
            raise EngineError(f"{META_FILE} has no class list — the model is unusable.")
        return cls(
            classes=[str(c) for c in classes],
            input_size=int(data.get("input_size", 64)),
            mean=float(data.get("mean", 0.5)),
            std=float(data.get("std", 0.25)),
            trained_at=float(data.get("trained_at", 0.0)),
            samples=int(data.get("samples", 0)),
            accuracy=float(data.get("accuracy", 0.0)),
            note=str(data.get("note", "")),
        )


def parse_class(label: str) -> tuple[str, int]:
    """`"d20:14"` → `("d20", 14)`. Raises on anything the dice vocabulary does not know."""
    kind, _, value = label.partition(":")
    try:
        parsed = int(value)
    except ValueError as exc:
        raise EngineError(f"{label!r} is not a valid class label (expected 'd20:14').") from exc
    if not is_valid(kind, parsed):
        raise EngineError(f"{label!r} is not a die this vocabulary knows.")
    return kind, parsed


def find_model(settings: Settings) -> Path | None:
    """The configured model, or the newest one in the models directory."""
    if settings.engine.model_path:
        path = Path(settings.engine.model_path)
        return path if (path / MODEL_FILE).is_file() else None
    root = settings.models_dir
    if not root.is_dir():
        return None
    bundles = [p for p in root.iterdir() if (p / MODEL_FILE).is_file()]
    return max(bundles, key=lambda p: (p / MODEL_FILE).stat().st_mtime, default=None)


class ModelEngine(Engine):
    name = "model"

    def __init__(self, settings: Settings, model_dir: Path | None = None) -> None:
        self.settings = settings
        bundle = model_dir or find_model(settings)
        if bundle is None:
            raise EngineError(
                "No trained model found. Collect labelled rolls under Training and train one "
                "— until then the classic engine reads pipped dice."
            )
        self.bundle = Path(bundle)
        try:
            self.meta = ModelMeta.from_json(json.loads((self.bundle / META_FILE).read_text()))
        except (OSError, ValueError) as exc:
            raise EngineError(f"{self.bundle / META_FILE} is unreadable: {exc}") from exc

        try:
            import onnxruntime
        except ImportError as exc:
            raise EngineError(
                "onnxruntime is not installed, so a trained model cannot run here. "
                "`pip install 'dicecore[model]'` — there are no ARMv6 wheels, so on a Pi Zero "
                "v1 use engine.mode=remote instead."
            ) from exc
        self._session = onnxruntime.InferenceSession(
            str(self.bundle / MODEL_FILE), providers=["CPUExecutionProvider"]
        )
        self._input = self._session.get_inputs()[0].name
        # Stage (a): the classic engine's segmentation, without its pip counting.
        self._segmenter = ClassicEngine(settings)

    def read(self, frame: Frame) -> RollResult:
        import numpy as np

        started = time.perf_counter()
        if frame.image is None:
            raise EngineError("The model engine needs decoded pixels, not just a JPEG.")

        # Stage (a). The classic pass already located every die; its pip counts are thrown
        # away, because the network reads pips too and reads them better.
        located = self._segmenter.read(frame)
        if not located.dice:
            located.engine = self.name
            return located

        crops = [self.crop(frame.image, d) for d in located.dice]
        batch = np.stack(crops).astype(np.float32)
        logits = self._session.run(None, {self._input: batch})[0]
        probabilities = _softmax(logits)

        dice: list[Die] = []
        for die, row in zip(located.dice, probabilities, strict=True):
            order = list(np.argsort(row)[::-1])
            best = int(order[0])
            kind, value = parse_class(self.meta.classes[best])
            alternatives = []
            for index in order[1:3]:
                other_kind, other_value = parse_class(self.meta.classes[int(index)])
                if other_kind == kind:
                    alternatives.append(other_value)
            dice.append(Die(kind, value, die.box, round(float(row[best]), 3), alternatives))

        warnings = [w for w in located.warnings if "pip counting" not in w]
        weak = [d for d in dice if d.confidence < self.settings.engine.min_confidence]
        if weak:
            warnings.append(
                f"{len(weak)} of {len(dice)} dice were read with low confidence. Confirm them "
                "under Training — a corrected roll is exactly the sample the model is missing."
            )
        return RollResult(
            dice=dice,
            engine=self.name,
            took_ms=round((time.perf_counter() - started) * 1000, 2),
            warnings=warnings,
        )

    def crop(self, image: Any, die: Die) -> Any:
        """
        One die as the network wants it: square, padded, grayscale, normalised.

        Training uses this same function. If the two ever drift apart the model degrades
        quietly rather than failing, which is the worst possible failure — so this lives in
        one place and both sides import it.
        """
        return prepare_crop(image, die.box, self.meta.input_size, self.meta.mean, self.meta.std)

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name, "bundle": str(self.bundle), "classes": len(self.meta.classes),
            "accuracy": self.meta.accuracy, "samples": self.meta.samples,
            "trained_at": self.meta.trained_at,
        }


def prepare_crop(image: Any, box: Any, size: int, mean: float, std: float) -> Any:
    """Shared by training and inference. See `ModelEngine.crop`."""
    import cv2
    import numpy as np

    h, w = image.shape[:2]
    # A square window around the die's centre, so the network never sees a die stretched by
    # a non-square bounding box — a tilted d20 is exactly where that would matter most.
    side = int(max(box.w, box.h) * 1.15)
    cx, cy = box.center
    x0 = max(0, min(w - 1, cx - side // 2))
    y0 = max(0, min(h - 1, cy - side // 2))
    x1 = max(x0 + 1, min(w, x0 + side))
    y1 = max(y0 + 1, min(h, y0 + side))
    patch = image[y0:y1, x0:x1]
    if patch.ndim == 3:
        patch = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)
    patch = cv2.resize(patch, (size, size), interpolation=cv2.INTER_AREA)
    normalised = (patch.astype(np.float32) / 255.0 - mean) / std
    return normalised[None, :, :]  # (1, size, size), channel first


def _softmax(logits: Any) -> Any:
    import numpy as np

    shifted = logits - logits.max(axis=1, keepdims=True)
    exponentials = np.exp(shifted)
    return exponentials / exponentials.sum(axis=1, keepdims=True)
