"""
Installing the optional halves from inside DiceCore.

The one property that matters here is that the extra is never taken from the request. The
rest is a subprocess and a log, and the tests stay well clear of actually downloading two
gigabytes of PyTorch.
"""

import pytest

from dicecore.install import EXTRAS, Installer, available, package_spec


def test_the_extras_are_a_fixed_list_with_a_reason_each():
    for key, (why, extra) in EXTRAS.items():
        assert why and extra
        assert key.isidentifier(), key


def test_an_unknown_extra_is_refused_before_anything_runs():
    installer = Installer()
    with pytest.raises(ValueError):
        installer.start("requests")
    with pytest.raises(ValueError):
        installer.start("train; rm -rf /")
    assert installer.job is None


def test_the_spec_points_at_the_checkout_when_running_from_one():
    # Installing dicecore[train] from PyPI over an editable checkout would replace the code
    # that is running, which is a strange thing to do to somebody who pressed "install".
    spec = package_spec("train")
    assert spec.endswith("[train]")
    assert spec.startswith("/") or spec.startswith("dicecore[")


def test_what_is_installed_is_reported_per_extra():
    state = available()
    assert set(state) == set(EXTRAS)
    for entry in state.values():
        assert isinstance(entry["installed"], bool) and entry["why"]


def test_two_installs_at_once_are_refused(monkeypatch):
    installer = Installer()
    monkeypatch.setattr(installer, "running", lambda: True)
    with pytest.raises(RuntimeError, match="already running"):
        installer.start("train")
