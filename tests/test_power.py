"""
The restart button, which is the way back into a box with no keyboard and no screen.

Nothing here reboots anything: the command is chosen and scheduled through injected seams,
because the one thing this module must never do while under test is what it is for.
"""

import pytest

from dicecore.system import power


class FakeTimer:
    fired: list[tuple[float, object]] = []

    def __init__(self, delay, function):
        self.delay, self.function = delay, function
        self.daemon = False

    def start(self):
        FakeTimer.fired.append((self.delay, self.function))


@pytest.fixture(autouse=True)
def _no_timers():
    FakeTimer.fired = []
    yield
    FakeTimer.fired = []


def test_the_first_installed_tool_wins(monkeypatch):
    monkeypatch.setattr(power.shutil, "which", lambda name: name == "shutdown")
    assert power.command_for("reboot") == ("shutdown", "-r", "now")


def test_a_machine_with_none_of_them_says_so_rather_than_pretending(monkeypatch):
    monkeypatch.setattr(power.shutil, "which", lambda name: None)
    with pytest.raises(power.PowerError) as caught:
        power.command_for("reboot")
    assert "from a shell" in str(caught.value)


def test_an_unknown_action_is_refused():
    with pytest.raises(power.PowerError):
        power.command_for("format-the-disk")


def test_scheduling_returns_before_anything_happens(monkeypatch):
    # The whole point of the delay: the browser has to get its answer, or a reboot that
    # worked perfectly reads as a network error and gets pressed a second time.
    monkeypatch.setattr(power.shutil, "which", lambda name: "/usr/bin/" + name)
    assert power.schedule("reboot", timer=FakeTimer) == ("systemctl", "reboot")
    assert len(FakeTimer.fired) == 1
    assert FakeTimer.fired[0][0] > 0


def test_restarting_a_service_nobody_is_supervising_is_refused(monkeypatch):
    # systemd would bring us back; a `dicecore serve` typed into a terminal would not, and
    # the page would go dark for good.
    monkeypatch.setattr(power.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(power, "service_is_managed", lambda: False)
    with pytest.raises(power.PowerError) as caught:
        power.schedule("service", timer=FakeTimer)
    assert "started by hand" in str(caught.value)
    assert FakeTimer.fired == []
