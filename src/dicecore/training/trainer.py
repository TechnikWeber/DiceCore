"""
The training run itself.

A small convolutional classifier over 64×64 grayscale die crops. Small on purpose: the
result has to run on a Pi 4 in a few milliseconds, and a dataset of a few thousand crops
from one evening of rolling cannot feed anything bigger without memorising it.

**Rotation is the augmentation that matters.** A die lands in any orientation, so the
network must be rotation-invariant — and it can be, even for 6 vs 9, because dice settle
that question with an underline that rotates along with the numeral. Without full 360°
rotation the model learns the orientation of your tower instead of the shape of the digits.

PyTorch is imported inside the functions. The module must stay importable on a Pi that will
never train, because the UI has to be able to explain *why* the Train button is disabled.
"""

from __future__ import annotations

import json
import math
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..dataset.store import DatasetStore
from ..engine.model import META_FILE, MODEL_FILE, ModelMeta
from .data import build_arrays

INPUT_SIZE = 64
MEAN, STD = 0.5, 0.25


def torch_available() -> tuple[bool, str]:
    try:
        import torch  # noqa: F401
    except ImportError as exc:
        return False, (
            f"PyTorch is not installed here ({exc}). Training runs on a PC: "
            "`pip install 'dicecore[train]'`. Collecting rolls works on any machine, and the "
            "trained model runs on a Pi 4/5 or through engine.mode=remote."
        )
    return True, ""


def build_model(num_classes: int) -> Any:
    """
    Four small conv blocks and a global average pool.

    Global average pooling instead of a flatten so the model does not encode *where* in the
    crop a feature was — a die is centred but never perfectly, and a flatten would happily
    learn the framing of one particular tower.
    """
    import torch.nn as nn

    def block(in_ch: int, out_ch: int) -> nn.Sequential:
        return nn.Sequential(
            nn.Conv2d(in_ch, out_ch, 3, padding=1, bias=False),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_ch, out_ch, 3, padding=1, bias=False),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
        )

    return nn.Sequential(
        block(1, 32), block(32, 64), block(64, 128),
        nn.AdaptiveAvgPool2d(1), nn.Flatten(),
        nn.Dropout(0.25), nn.Linear(128, num_classes),
    )


def augment(batch: Any) -> Any:
    """Random rotation, shift, scale and brightness — applied on the GPU-less CPU path too."""
    import torch
    import torch.nn.functional as functional

    n = batch.shape[0]
    angles = torch.rand(n) * 2 * math.pi
    scale = 0.9 + torch.rand(n) * 0.25
    shift = (torch.rand(n, 2) - 0.5) * 0.16
    cos, sin = torch.cos(angles) / scale, torch.sin(angles) / scale
    theta = torch.zeros(n, 2, 3)
    theta[:, 0, 0], theta[:, 0, 1], theta[:, 0, 2] = cos, -sin, shift[:, 0]
    theta[:, 1, 0], theta[:, 1, 1], theta[:, 1, 2] = sin, cos, shift[:, 1]
    grid = functional.affine_grid(theta, list(batch.shape), align_corners=False)
    # `border` padding, not zeros: a zero corner is a black triangle the network would
    # gladly use to read the rotation angle off the augmentation itself.
    out = functional.grid_sample(batch, grid, align_corners=False, padding_mode="border")
    out = out * (0.8 + torch.rand(n, 1, 1, 1) * 0.4) + (torch.rand(n, 1, 1, 1) - 0.5) * 0.3
    return out


def train_model(
    store: DatasetStore,
    sets: str | list[str],
    out_dir: Path,
    epochs: int = 30,
    batch_size: int = 32,
    learning_rate: float = 2e-3,
    validation_split: float = 0.2,
    progress: Callable[[dict[str, Any]], None] | None = None,
    should_stop: Callable[[], bool] = lambda: False,
) -> ModelMeta:
    """
    Train, evaluate, export ONNX, write the bundle. Returns the metadata it wrote.

    `progress` is called after every epoch with numbers the UI charts; `should_stop` lets
    the user cancel a run that is clearly going nowhere without killing the service.
    """
    import numpy as np
    import torch
    from torch.utils.data import DataLoader, TensorDataset

    def emit(**fields: Any) -> None:
        if progress:
            progress(fields)

    emit(stage="loading", message="Reading confirmed rolls…")
    from .data import as_ids

    set_ids = as_ids(sets)
    features, labels, classes = build_arrays(store, set_ids, INPUT_SIZE, MEAN, STD)
    emit(stage="loading", message=f"{len(labels)} dice, {len(classes)} faces",
         samples=len(labels), classes=classes)

    # Split per class, not at random: a random split of a small set can leave a rare face
    # entirely out of validation, and then the accuracy number is about the common faces.
    generator = np.random.default_rng(0)
    train_idx, val_idx = [], []
    for class_index in range(len(classes)):
        members = np.nonzero(labels == class_index)[0]
        generator.shuffle(members)
        cut = max(1, int(len(members) * validation_split)) if len(members) > 2 else 0
        val_idx.extend(members[:cut])
        train_idx.extend(members[cut:])

    x_train = torch.from_numpy(features[train_idx])
    y_train = torch.from_numpy(labels[train_idx])
    x_val = torch.from_numpy(features[val_idx]) if val_idx else x_train[:1]
    y_val = torch.from_numpy(labels[val_idx]) if val_idx else y_train[:1]

    model = build_model(len(classes))
    optimiser = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=1e-4)
    schedule = torch.optim.lr_scheduler.CosineAnnealingLR(optimiser, T_max=max(1, epochs))
    loss_fn = torch.nn.CrossEntropyLoss(label_smoothing=0.05)
    loader = DataLoader(TensorDataset(x_train, y_train), batch_size=batch_size, shuffle=True)

    best_accuracy = 0.0
    best_state = {k: v.clone() for k, v in model.state_dict().items()}
    for epoch in range(1, epochs + 1):
        if should_stop():
            emit(stage="cancelled", message=f"Stopped after {epoch - 1} epochs.")
            break
        model.train()
        running = 0.0
        for xb, yb in loader:
            optimiser.zero_grad()
            loss = loss_fn(model(augment(xb)), yb)
            loss.backward()
            optimiser.step()
            running += float(loss) * len(xb)
        schedule.step()

        model.eval()
        with torch.no_grad():
            predicted = model(x_val).argmax(dim=1)
            accuracy = float((predicted == y_val).float().mean())
        if accuracy >= best_accuracy:
            best_accuracy = accuracy
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
        emit(stage="training", epoch=epoch, epochs=epochs,
             loss=round(running / max(1, len(train_idx)), 4),
             accuracy=round(accuracy, 4), best=round(best_accuracy, 4))

    model.load_state_dict(best_state)
    model.eval()

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    emit(stage="exporting", message="Writing model.onnx…")
    dummy = torch.zeros(1, 1, INPUT_SIZE, INPUT_SIZE)
    torch.onnx.export(
        model, dummy, str(out_dir / MODEL_FILE),
        input_names=["crop"], output_names=["logits"],
        # A whole roll is classified in one call, so the batch axis must stay dynamic.
        dynamic_axes={"crop": {0: "batch"}, "logits": {0: "batch"}},
        opset_version=17,
    )
    meta = ModelMeta(
        classes=classes, input_size=INPUT_SIZE, mean=MEAN, std=STD,
        trained_at=time.time(), samples=int(len(labels)), accuracy=round(best_accuracy, 4),
        note=f"sets={','.join(set_ids)}, epochs={epochs}",
    )
    (out_dir / META_FILE).write_text(json.dumps(meta.to_json(), indent=2) + "\n")
    emit(stage="done", message=f"Validation accuracy {best_accuracy:.1%}",
         accuracy=round(best_accuracy, 4), path=str(out_dir))
    return meta
