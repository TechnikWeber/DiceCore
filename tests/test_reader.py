"""
The reader's own two checks: is this a new throw, and is the camera still showing me the
world? Both are about the relationship between *this* roll and the previous one, so neither
can live in the guard, which only ever sees one hold window.
"""

import pytest

pytest.importorskip("cv2")
np = pytest.importorskip("numpy")

from dicecore.capture.base import FrameSource  # noqa: E402
from dicecore.config import Settings  # noqa: E402
from dicecore.dice import Frame  # noqa: E402
from dicecore.reader import Reader  # noqa: E402
from dicecore.synth import render_scene  # noqa: E402


class StillSource(FrameSource):
    """A camera pointed at a tray nobody touches."""

    name = "still"

    def __init__(self, image, live: bool = True, noise: bool = False) -> None:
        self.image = image
        self.is_live = live
        self.noise = noise
        self.grabs = 0

    def grab(self) -> Frame:
        self.grabs += 1
        if not self.noise:
            return Frame(image=self.image.copy())
        grain = np.random.default_rng(self.grabs).integers(-2, 3, self.image.shape,
                                                           dtype=np.int16)
        return Frame(image=np.clip(self.image.astype(np.int16) + grain, 0, 255).astype(np.uint8))


def reader_over(source: StillSource, **guard) -> Reader:
    settings = Settings()
    settings.capture.source = "v4l2"          # anything but the folder simulator
    settings.settle.stable_frames = 2
    settings.guard.hold_s = 0.2
    settings.guard.interval_s = 0.05
    for key, value in guard.items():
        setattr(settings.guard, key, value)
    reader = Reader(settings)
    reader._source = source
    return reader


def tray():
    image, _ = render_scene([("d6", 4)], seed=3, width=400, height=300, die_px=60)
    return image


def test_the_same_dice_read_twice_are_marked_stale():
    # Reporting a lucky roll a second time without throwing again is the cheapest cheat
    # there is, and the only evidence is that nothing ever moved.
    reader = reader_over(StillSource(tray(), live=False, noise=True))
    first = reader.read()
    second = reader.read()
    assert not first.stale
    assert second.stale
    assert any("not a new throw" in w for w in second.warnings)


def test_a_stale_reading_still_reports_the_number():
    # Display modes look at the same settled dice all evening; staleness is information,
    # not a refusal.
    reader = reader_over(StillSource(tray(), live=False, noise=True))
    reader.read()
    second = reader.read()
    assert second.total == 4 and second.usable


def test_staleness_can_be_switched_off():
    reader = reader_over(StillSource(tray(), live=False, noise=True), require_throw=False)
    reader.read()
    assert not reader.read().stale


def test_a_live_camera_repeating_one_frame_exactly_is_reported_as_frozen():
    reader = reader_over(StillSource(tray(), live=True, noise=False), freeze_frames=99)
    reader.read()
    second = reader.read()
    kinds = [e["kind"] for e in second.integrity["events"]]
    assert "frozen" in kinds


def test_sensor_noise_alone_is_not_a_frozen_feed():
    reader = reader_over(StillSource(tray(), live=True, noise=True), freeze_frames=99)
    reader.read()
    second = reader.read()
    kinds = [e["kind"] for e in second.integrity["events"]]
    assert "frozen" not in kinds


def test_verify_false_hands_the_number_over_before_the_verdict():
    reader = reader_over(StillSource(tray(), live=False, noise=True))
    result = reader.read(verify=False)
    # Published but not yet judged: usable, and honest about which of the two it is.
    assert result.verdict == "pending" and result.integrity is None and result.usable


def test_the_verdict_can_be_collected_afterwards():
    reader = reader_over(StillSource(tray(), live=False, noise=True))
    reader.read(verify=False)
    verified = reader.verify_last()
    assert verified.verdict == "clean" and verified.integrity is not None
    # Asking twice changes nothing and costs nothing.
    assert reader.verify_last() is verified


def test_with_the_guard_off_a_roll_is_simply_unverified():
    reader = reader_over(StillSource(tray(), live=False, noise=True), enabled=False)
    result = reader.read()
    assert result.verdict == "unverified" and result.integrity is None


def test_a_watched_undisturbed_tray_comes_back_clean():
    reader = reader_over(StillSource(tray(), live=False, noise=True))
    result = reader.read()
    assert result.verdict == "clean" and result.usable
    assert result.integrity["seal"].startswith("sha256:")
