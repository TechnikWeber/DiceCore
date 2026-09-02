"""
Train, export, load, read — the whole chain, once.

This is the surface that had never been executed. It ran end to end for the first time on a
tiny synthetic dataset and immediately found two things: `torch.onnx.export` needs
`onnxscript`, which was missing from the `train` extra, so training completed and then
failed at the one step that produces a model; and the loss was being read off a tensor that
still carried a gradient.

Deliberately small and deliberately not about accuracy. A model trained on drawings learns
to read drawings; what is checked here is that the pipeline produces a loadable model and
that inference comes back in the shape the rest of DiceCore expects.
"""

import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("onnxruntime")
pytest.importorskip("cv2")

import cv2  # noqa: E402

from dicecore.config import Settings  # noqa: E402
from dicecore.dataset import DatasetStore  # noqa: E402
from dicecore.dice import Die, Frame, RollResult  # noqa: E402
from dicecore.engine.model import META_FILE, MODEL_FILE, ModelEngine, find_model  # noqa: E402
from dicecore.synth import render_scene  # noqa: E402
from dicecore.training.data import readiness  # noqa: E402
from dicecore.training.trainer import train_model  # noqa: E402


@pytest.fixture(scope="module")
def trained(tmp_path_factory):
    """Three faces, four examples each, four epochs. Enough to exercise every step."""
    root = tmp_path_factory.mktemp("pipeline")
    store = DatasetStore(root / "datasets")
    record = store.create_set("tiny")
    for value in (1, 3, 6):
        for n in range(4):
            image, truth = render_scene([("d6", value)], seed=value * 10 + n,
                                        width=300, height=240, die_px=90)
            sample = store.add_sample(record.id, cv2.imencode(".jpg", image)[1].tobytes(),
                                      RollResult(dice=[Die("d6", 0, truth[0].box,
                                                           confidence=0.0)]))
            store.update_sample(record.id, sample.id, [{"kind": "d6", "value": value}])
    out = root / "models" / "tiny"
    meta = train_model(store, record.id, out, epochs=4)
    return root, store, record, out, meta


def test_training_writes_a_model_and_its_description(trained):
    _, _, _, out, meta = trained
    assert (out / MODEL_FILE).is_file() and (out / META_FILE).is_file()
    assert sorted(meta.classes) == ["d6:1", "d6:3", "d6:6"]
    assert meta.samples == 12 and meta.input_size == 64


def test_the_class_order_is_the_network_output_order(trained):
    # Sorting or rebuilding this on load silently remaps every prediction.
    _, _, _, out, meta = trained
    import json

    written = json.loads((out / META_FILE).read_text())
    assert written["classes"] == meta.classes


def test_the_exported_model_loads_and_reads_dice(trained):
    root, _, _, out, _ = trained
    settings = Settings()
    settings.engine.model_path = str(out)
    engine = ModelEngine(settings, out)

    image, _ = render_scene([("d6", 6)], seed=999, width=800, height=600, die_px=95)
    result = engine.read(Frame(image=image))
    assert result.engine == "model"
    assert result.dice, "the model engine found no dice at all"
    die = result.dice[0]
    assert die.kind == "d6" and die.value in (1, 3, 6)
    assert 0.0 < die.confidence <= 1.0
    assert result.took_ms > 0


def test_a_whole_tray_is_classified_in_one_pass(trained):
    _, _, _, out, _ = trained
    settings = Settings()
    engine = ModelEngine(settings, out)
    image, _ = render_scene([("d6", 1), ("d6", 3), ("d6", 6)], seed=42,
                            width=900, height=600, die_px=95)
    result = engine.read(Frame(image=image))
    # The batch axis has to stay dynamic in the export, or a second die throws.
    assert len(result.dice) == 3


def test_the_engine_finds_the_model_without_being_told_where(trained):
    root, _, _, out, _ = trained
    settings = Settings()
    settings.engine.model_path = ""
    import os

    os.environ["DICECORE_STATE"] = str(root)
    try:
        assert find_model(settings) == out
    finally:
        os.environ.pop("DICECORE_STATE", None)


def test_training_refuses_a_set_that_cannot_teach_anything(trained):
    root, store, _, _, _ = trained
    empty = store.create_set("empty")
    state = readiness(store, empty.id)
    assert not state.ready and state.reasons
