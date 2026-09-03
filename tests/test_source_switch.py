"""
Real dice or simulated ones, as one switch.

The question at the table is "do we have a tower", and it has two answers — but `source` has
six values, so something has to remember which camera "real" meant. That is what this pins
down: switching to the simulator and back must land on the camera the box actually has, not
on a guess made twice.
"""

import pytest

from dicecore.capture import default_camera, use_simulator
from dicecore.capture.base import CaptureError, require_tuning_file
from dicecore.config import CaptureSettings


def test_the_simulator_is_the_default():
    # The one source that works on the first run with nothing plugged in and nothing
    # generated first. A camera is configured once; a first game should need no setup.
    assert CaptureSettings().source == "sim"


def test_switching_to_the_simulator_remembers_the_camera():
    capture = CaptureSettings(source="picamera2")
    assert use_simulator(capture, True) == "sim"
    assert capture.camera_source == "picamera2"
    assert use_simulator(capture, False) == "picamera2"


def test_an_arducam_box_comes_back_to_its_arducam():
    # The guess would be right on a plain Pi and wrong here, which is the whole reason the
    # previous source is written down rather than re-derived.
    capture = CaptureSettings(source="rpicam", csi_module="imx519")
    use_simulator(capture, True)
    use_simulator(capture, False)
    assert capture.source == "rpicam" and capture.csi_module == "imx519"


def test_switching_to_the_simulator_twice_does_not_forget_the_camera():
    capture = CaptureSettings(source="v4l2")
    use_simulator(capture, True)
    use_simulator(capture, True)
    assert capture.camera_source == "v4l2"
    assert use_simulator(capture, False) == "v4l2"


def test_a_box_that_has_never_had_a_camera_gets_the_one_it_probably_has():
    assert default_camera(is_pi=True) == "picamera2"
    assert default_camera(is_pi=False) == "v4l2"
    fresh = CaptureSettings()
    assert use_simulator(fresh, False, is_pi=True) == "picamera2"
    # And the guess is written down, so the next round trip is stable rather than re-guessed.
    assert fresh.camera_source == "picamera2"


def test_a_remembered_simulator_is_not_a_camera():
    # Nothing should be able to leave the switch pointing at "real dice" and the simulator
    # at the same time.
    capture = CaptureSettings(source="sim", camera_source="sim")
    assert use_simulator(capture, False) != "sim"


# --- tuning files ------------------------------------------------------------


def test_a_tuning_file_that_is_not_there_is_named_before_libcamera_hides_it(tmp_path):
    # libcamera does not fall back: it fails to load the IPA, drops the sensor, and
    # rpicam-still reports "no cameras available" — indistinguishable from an unplugged
    # ribbon cable, for what is really a wrong path in a text field.
    with pytest.raises(CaptureError) as caught:
        require_tuning_file(str(tmp_path / "gone.json"))
    assert "does not exist" in str(caught.value)
    assert "no cameras available" in str(caught.value)


def test_no_tuning_file_is_the_normal_case_and_not_an_error(tmp_path):
    require_tuning_file("")
    present = tmp_path / "there.json"
    present.write_text("{}")
    require_tuning_file(str(present))
