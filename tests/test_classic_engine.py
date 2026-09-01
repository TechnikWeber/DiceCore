"""
Recognition tests on synthetic scenes.

Photographs cannot be committed to a repo in useful numbers, so the suite renders its own
dice. These are not training data and they do not prove the engine works on a real tower —
they prove the pipeline (segmentation, pip counting, ordering, confidence) does what it
claims, and they catch the regressions that would otherwise only show up on hardware.
"""

import random

import pytest

from dicecore.config import Settings
from dicecore.dice import Frame
from dicecore.engine.classic import ClassicEngine
from dicecore.synth import render_scene

pytest.importorskip("cv2")


@pytest.fixture
def engine() -> ClassicEngine:
    return ClassicEngine(Settings())


def read(engine: ClassicEngine, spec, seed: int = 0, **kwargs):
    image, truth = render_scene(spec, seed=seed, **kwargs)
    return engine.read(Frame(image=image)), truth


def test_a_single_die_is_counted(engine):
    for value in range(1, 7):
        result, _ = read(engine, [("d6", value)], seed=value)
        assert [d.value for d in result.dice] == [value]


def test_forty_random_scenes_of_pipped_dice_are_read_exactly(engine):
    rng = random.Random(0)
    for seed in range(40):
        spec = [("d6", rng.randint(1, 6)) for _ in range(rng.randint(1, 4))]
        result, truth = read(engine, spec, seed=seed)
        assert sorted(d.value for d in result.dice) == sorted(t.value for t in truth), seed


def test_the_total_is_the_sum_of_the_dice(engine):
    result, truth = read(engine, [("d6", 5), ("d6", 3), ("d6", 6)], seed=4)
    assert result.total == sum(t.value for t in truth)


def test_numeral_dice_are_located_but_not_guessed_at(engine):
    # The classic engine reads pips only. Reporting a confident wrong number would be worse
    # than admitting it needs a model — and the admission is what feeds the label loop.
    result, _ = read(engine, [("d6", 4), ("d20", 14), ("d12", 11)], seed=7,
                     width=800, height=500)
    assert len(result.dice) == 3
    read_dice = [d for d in result.dice if d.value]
    assert [d.value for d in read_dice] == [4]
    assert all(d.confidence == 0.0 for d in result.dice if not d.value)
    assert any("pip counting" in w for w in result.warnings)


def test_an_empty_tray_reads_as_nothing_and_says_why(engine):
    result, _ = read(engine, [], seed=1)
    assert result.dice == [] and result.total == 0
    assert any("No dice found" in w for w in result.warnings)


def test_confidence_is_reported_for_every_die(engine):
    result, _ = read(engine, [("d6", 2), ("d6", 6)], seed=9)
    assert all(0.0 < d.confidence <= 1.0 for d in result.dice)


def test_the_tray_region_excludes_what_lies_outside_it():
    settings = Settings()
    settings.tray.x, settings.tray.y, settings.tray.w, settings.tray.h = 0.0, 0.0, 0.45, 1.0
    engine = ClassicEngine(settings)
    image, truth = render_scene([("d6", 3), ("d6", 5)], seed=11, width=800, height=600)
    inside = [t for t in truth if t.box.center[0] < 0.45 * 800]
    result = engine.read(Frame(image=image))
    assert len(result.dice) == len(inside)


def test_boxes_are_reported_in_full_frame_coordinates():
    settings = Settings()
    settings.tray.x, settings.tray.w = 0.2, 0.8
    engine = ClassicEngine(settings)
    image, truth = render_scene([("d6", 4)], seed=13, width=800, height=600)
    result = engine.read(Frame(image=image))
    if result.dice and truth:
        # Within a few pixels of where the die was actually drawn, not of the crop.
        assert abs(result.dice[0].box.center[0] - truth[0].box.center[0]) < 15
