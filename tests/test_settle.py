"""Settle detection, run in fake time so the suite does not actually wait for dice."""

import pytest

from dicecore.config import SettleSettings
from dicecore.dice import Frame

pytest.importorskip("cv2")
np = pytest.importorskip("numpy")

from dicecore.capture.settle import wait_for_settle  # noqa: E402


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def sleep(self, seconds: float) -> None:
        self.now += seconds

    def time(self) -> float:
        return self.now


def still_frame(shade: int = 120) -> Frame:
    return Frame(image=np.full((60, 80, 3), shade, dtype=np.uint8))


def test_a_still_scene_settles_after_the_required_frames():
    clock = Clock()
    outcome = wait_for_settle(still_frame, SettleSettings(stable_frames=3), clock.sleep, clock.time)
    assert outcome.settled and outcome.warning is None
    assert outcome.frames_seen == 4  # the first grab plus three quiet ones


def test_a_tumbling_scene_times_out_and_says_so():
    clock = Clock()
    shades = iter(range(0, 255, 40))

    def moving() -> Frame:
        return still_frame(next(shades, 250))

    outcome = wait_for_settle(moving, SettleSettings(timeout_s=0.2, motion_threshold=1.0),
                              clock.sleep, clock.time)
    assert not outcome.settled
    assert "still have been rolling" in (outcome.warning or "")


def test_settling_can_be_switched_off_entirely():
    outcome = wait_for_settle(still_frame, SettleSettings(enabled=False))
    assert outcome.settled and outcome.frames_seen == 1
