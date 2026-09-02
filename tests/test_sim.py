"""
Dice without dice.

The simulator exists so that somebody with no tower, no camera or nobody in the room can
still play — and so two people can play each other over the network without either owning
hardware. It renders a real picture and reads it back through the real engine, which is what
these tests are actually checking: that nothing downstream can tell the difference.
"""

import pytest

pytest.importorskip("cv2")

from dicecore.capture import open_source  # noqa: E402
from dicecore.capture.base import CaptureError  # noqa: E402
from dicecore.capture.sim import SimSource, require_sim  # noqa: E402
from dicecore.config import Settings  # noqa: E402
from dicecore.play.turns import TurnRules  # noqa: E402
from dicecore.reader import Reader  # noqa: E402


def test_nothing_is_thrown_until_somebody_asks():
    source = SimSource(seed=1)
    first = source.grab()
    second = source.grab()
    # The same tray, not a new roll. A simulator that rolled every time it was looked at
    # would be a random number generator with a picture attached.
    assert first is second
    assert source.throws == 0


def test_throwing_changes_the_picture():
    source = SimSource(seed=1)
    source.set_plan(["d6"], 5)
    before = source.grab().image.copy()
    source.throw()
    assert source.throws == 1
    assert not (before == source.grab().image).all()


def test_the_plan_comes_from_the_game():
    source = SimSource(seed=1)
    source.set_plan(["d6"], 5)
    assert source.plan == ["d6"] * 5
    # Several kinds is a roleplaying throw: the workhorse plus one of each of the others.
    source.set_plan(["d20", "d6"], 3)
    assert source.plan[0] == "d20" and len(source.plan) == 3


def test_a_plan_is_kept_within_reason():
    source = SimSource(seed=1)
    source.set_plan(["d6"], 500)
    assert len(source.plan) == 12
    source.set_plan(["nonsense"], 3)
    assert set(source.plan) == {"d6"}


def test_it_is_not_a_live_source():
    # The frozen-feed check looks for byte-identical captures, which is precisely what a
    # simulator does on purpose between throws. Flagging that would void every roll.
    assert SimSource().is_live is False


def test_asking_a_camera_to_throw_says_what_to_do_instead(tmp_path):
    from dicecore.synth import write_scenes

    frames = tmp_path / "frames"
    write_scenes(frames, count=2, kinds=("d6",))
    settings = Settings()
    settings.capture.source = "folder"
    settings.capture.folder = str(frames)
    source = open_source(settings, None)
    with pytest.raises(CaptureError) as raised:
        require_sim(source)
    assert "Setup" in str(raised.value)


@pytest.fixture
def reader(tmp_path, monkeypatch):
    monkeypatch.setenv("DICECORE_STATE", str(tmp_path))
    settings = Settings()
    settings.state_dir = str(tmp_path)
    settings.capture.source = "sim"
    settings.engine.expected_kinds = ["d6"]
    settings.guard.enabled = False
    return Reader(settings)


def test_a_thrown_roll_is_read_the_same_way_a_real_one_is(reader):
    assert reader.can_throw()
    result = reader.throw()
    assert result.count >= 1
    assert result.total == sum(d.value for d in result.dice)
    assert all(1 <= die.value <= 6 for die in result.dice)


def test_the_game_decides_how_many_dice(reader):
    reader.game.start("yahtzee", TurnRules(rolls=3, holds=True), ["Player 1"])
    assert reader.dice_wanted() == 5
    assert reader.throw().count == 5


def test_a_guest_throws_the_pool_it_was_given(reader):
    # There is no game on a guest's own instance, so the host says how many. Passing three
    # must mean three even though nothing local asked for that.
    assert reader.throw(count=3).count == 3


def test_the_same_dice_come_back_until_they_are_thrown_again(reader):
    reader.game.start("yahtzee", TurnRules(rolls=3, holds=True), ["Player 1"])
    first = reader.throw()
    again = reader.read(wait_for_still=False)
    assert [d.value for d in again.dice] == [d.value for d in first.dice]
    # And the game is not fooled into spending a second throw on a tray nobody touched.
    assert again.stale is True
    assert reader.game.turn.rolls_used == 1


def test_a_camera_cannot_be_asked_to_roll(tmp_path, monkeypatch):
    from dicecore.synth import write_scenes

    monkeypatch.setenv("DICECORE_STATE", str(tmp_path))
    frames = tmp_path / "frames"
    write_scenes(frames, count=2, kinds=("d6",))
    settings = Settings()
    settings.state_dir = str(tmp_path)
    settings.capture.source = "folder"
    settings.capture.folder = str(frames)
    reader = Reader(settings)
    assert reader.can_throw() is False
    with pytest.raises(CaptureError):
        reader.throw()


# --- keeping dice back -----------------------------------------------------------------


def test_a_held_die_is_not_thrown_again():
    source = SimSource(seed=7)
    source.set_plan(["d6"], 5)
    source.throw()
    source.grab()                                     # renders, which is what fixes places
    before = list(source._values)

    source.throw([True, True, False, False, False])
    # The first two are the same dice: not re-rolled, and not re-ordered past each other.
    assert source._values[:2] == before[:2]
    assert len(source._values) == 5


def test_a_held_die_stays_exactly_where_it_was():
    """The only signal that a die was held is that it did not move. If the simulator moves
    it, the reader sees a fresh throw and the hold silently disappears."""
    source = SimSource(seed=3)
    source.set_plan(["d6"], 5)
    source.throw()
    source.grab()
    kept = source._places[0]

    source.throw([True] + [False] * 4)
    source.grab()
    assert source._places[0] == kept


def test_nothing_held_means_everything_is_thrown():
    source = SimSource(seed=11)
    source.set_plan(["d6"], 5)
    source.throw()
    source.grab()
    before = list(source._values)
    for _ in range(6):
        source.throw()
        source.grab()
        if list(source._values) != before:
            return
    raise AssertionError("six throws in a row came out identical — nothing is being rolled")


def test_the_engine_reads_a_held_die_back_as_held(reader):
    """The whole round trip: hold, throw, and the game still says it is being kept."""
    reader.game.start("yahtzee", TurnRules(rolls=3, holds=True), ["Player 1"])
    reader.throw()
    assert len(reader.game.turn.dice) == 5
    reader.game.hold(0)
    reader.game.hold(1)
    kept = sorted(slot.value for slot in reader.game.turn.dice if slot.held)

    reader.throw()
    still = sorted(slot.value for slot in reader.game.turn.dice if slot.held)
    assert still == kept
    assert reader.game.turn.rolls_used == 2


def test_a_new_turn_throws_everything(reader):
    # Holds belong to a turn. Picking the dice up is what starting one means.
    reader.game.start("yahtzee", TurnRules(rolls=3, holds=True), ["Player 1"])
    reader.throw()
    reader.game.hold(0)
    reader.game.book("chance")
    assert reader.held_now() == []
    reader.throw()
    assert not any(slot.held for slot in reader.game.turn.dice)


def test_farkle_sets_dice_aside_rather_than_keeping_them_on_the_tray(reader):
    # Opposite rule, same word: a die set aside in Farkle leaves the tray, so the next throw
    # is fewer dice — never the same pool with some of it standing still.
    reader.game.start("farkle", TurnRules(rolls=1, holds=True, unlimited=True), ["Player 1"])
    reader.throw()
    reader.game.hold(0)
    assert reader.held_now() == []
