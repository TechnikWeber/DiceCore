"""
Fair play, tested by staging the cheating.

The guard's job is to tell three situations apart: nothing happened, something happened but
the dice are unchanged, and the dice are not what was published. Each of those is staged
here with scripted frames and fake time, so a two-second hold window costs the suite
nothing and the edges are actually exercised.
"""

import pytest

pytest.importorskip("cv2")
np = pytest.importorskip("numpy")

from dicecore.config import GuardSettings  # noqa: E402
from dicecore.dice import Box, Die, Frame  # noqa: E402
from dicecore.guard import (  # noqa: E402
    TamperGuard,
    change_boxes,
    describe_change,
    touches_border,
)
from dicecore.integrity import CLEAN, DISTURBED, UNVERIFIED, VOID  # noqa: E402
from dicecore.synth import render_scene  # noqa: E402


class Clock:
    """Fake time, so a hold window runs instantly."""

    def __init__(self) -> None:
        self.now = 0.0

    def sleep(self, seconds: float) -> None:
        self.now += seconds

    def time(self) -> float:
        return self.now


def scene(spec=(("d6", 4),), seed: int = 3):
    image, truth = render_scene(list(spec), seed=seed, width=400, height=300, die_px=60)
    dice = [Die(t.kind, t.value, t.box, 0.95) for t in truth]
    return Frame(image=image), dice


def with_hand(frame: Frame) -> Frame:
    """The same tray with an arm reaching in from the left edge."""
    image = frame.image.copy()
    image[80:220, 0:170] = 90
    return Frame(image=image)


def settings(**overrides) -> GuardSettings:
    base = GuardSettings(hold_s=0.5, interval_s=0.1, freeze_frames=3)
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def run(frames, sealed, reread, cfg) -> "object":
    """Drive one hold window over a scripted list of frames."""
    sequence = iter(frames)
    clock = Clock()

    def grab():
        return next(sequence, frames[-1])

    return TamperGuard(cfg).watch(
        grab=grab, reread=reread, sealed=sealed, reference=frames[0],
        jpeg=b"frame", live=True, sleep=clock.sleep, now=clock.time,
    )


# --- the pixel helpers ------------------------------------------------------------


def test_a_change_is_found_where_the_picture_actually_changed():
    frame, _ = scene()
    from dicecore.capture.settle import prepare

    before = prepare(frame.image)
    after = prepare(with_hand(frame).image)
    boxes = change_boxes(before, after)
    assert boxes and boxes[0].area > 100


def test_a_region_reaching_the_frame_edge_is_recognised_as_coming_from_outside():
    assert touches_border(Box(0, 40, 60, 60), 160, 120)
    assert not touches_border(Box(40, 40, 30, 30), 160, 120)


def test_a_big_border_touching_change_is_called_a_reach_a_small_one_is_not():
    kind, wording = describe_change([Box(0, 0, 80, 90)], 160, 120, 0.05)
    assert kind == "reach" and "outside" in wording
    kind, _ = describe_change([Box(60, 50, 8, 8)], 160, 120, 0.05)
    assert kind == "motion"
    assert describe_change([], 160, 120, 0.05)[0] == "motion"


# --- the three situations ---------------------------------------------------------


def test_an_undisturbed_tray_is_clean():
    frame, dice = scene()
    integrity = run([frame] * 8, dice, lambda f: dice, settings(freeze_frames=99))
    assert integrity.verdict == CLEAN
    assert integrity.events == []
    assert integrity.settled_check and integrity.seal.startswith("sha256:")


def test_a_hand_over_an_unchanged_tray_is_flagged_but_still_usable():
    # Someone reaching past the tower for their drink must not throw away a good roll.
    frame, dice = scene()
    frames = [frame, frame, with_hand(frame), with_hand(frame), frame, frame]
    integrity = run(frames, dice, lambda f: dice, settings())
    assert integrity.verdict == DISTURBED
    kinds = {e.kind for e in integrity.events}
    assert "reach" in kinds and "unchanged" in kinds


def test_a_die_that_changed_after_the_reading_voids_the_roll():
    frame, dice = scene()
    turned = [Die("d6", 6, dice[0].box, 0.95)]
    frames = [frame, with_hand(frame), frame]
    integrity = run(frames, dice, lambda f: turned, settings(policy="void"))
    assert integrity.verdict == VOID
    assert any(e.kind == "changed" for e in integrity.events)
    assert any("now read d6:6" in e.detail for e in integrity.events)


def test_the_same_change_only_flags_under_the_reporting_policy():
    frame, dice = scene()
    turned = [Die("d6", 6, dice[0].box, 0.95)]
    integrity = run([frame, with_hand(frame), frame], dice, lambda f: turned,
                    settings(policy="flag"))
    assert integrity.verdict == DISTURBED  # reported, marked, not withheld


def test_a_die_removed_from_the_tray_is_caught():
    frame, dice = scene([("d6", 4), ("d6", 2)], seed=5)
    integrity = run([frame, with_hand(frame), frame], dice, lambda f: dice[:1],
                    settings(policy="void"))
    assert integrity.verdict == VOID
    assert any("on the tray now" in e.detail for e in integrity.events)


def test_a_nudged_die_is_caught_even_when_it_shows_the_same_face():
    frame, dice = scene()
    moved = [Die(dice[0].kind, dice[0].value,
                 Box(dice[0].box.x + 60, dice[0].box.y, dice[0].box.w, dice[0].box.h), 0.95)]
    integrity = run([frame, with_hand(frame), frame], dice, lambda f: moved,
                    settings(policy="void"))
    assert integrity.verdict == VOID
    assert any("without changing face" in e.detail for e in integrity.events)


# --- attacks on the watcher itself ------------------------------------------------


def test_a_frozen_feed_is_a_fault_not_a_clean_tray():
    # Identical captures cannot happen with a real sensor, so this is the one way to fool a
    # watcher from outside — and it is exactly what it looks like.
    frame, dice = scene()
    integrity = run([frame] * 8, dice, lambda f: dice, settings(freeze_frames=3, policy="void"))
    assert integrity.verdict == VOID
    assert any(e.kind == "frozen" for e in integrity.events)


def test_a_source_that_is_not_live_is_not_accused_of_freezing():
    # The folder simulator hands out the same image on purpose while the tray is held.
    frame, dice = scene()
    sequence = iter([frame] * 8)
    clock = Clock()
    integrity = TamperGuard(settings(freeze_frames=2)).watch(
        grab=lambda: next(sequence, frame), reread=lambda f: dice, sealed=dice,
        reference=frame, jpeg=b"x", live=False, sleep=clock.sleep, now=clock.time)
    assert integrity.verdict == CLEAN


def test_a_still_tray_at_full_resolution_is_not_mistaken_for_a_frozen_feed():
    # The trap this check fell into once: after downscaling and blurring, two genuinely
    # different captures of a quiet table are identical, and every roll came out "frozen".
    frame, dice = scene()
    # Eight captures of one motionless tray, differing only by sensor noise — which is what
    # a real camera hands you and what makes a genuine freeze recognisable.
    noisy = []
    for seed in range(8):
        grain = np.random.default_rng(seed).integers(-2, 3, frame.image.shape, dtype=np.int16)
        noisy.append(Frame(image=np.clip(frame.image.astype(np.int16) + grain, 0, 255)
                           .astype(np.uint8)))
    integrity = run(noisy, dice, lambda f: dice, settings(freeze_frames=3))
    assert not any(e.kind == "frozen" for e in integrity.events)


def test_a_covered_lens_is_a_fault():
    frame, dice = scene()
    dark = Frame(image=(frame.image * 0.1).astype(np.uint8))
    integrity = run([frame, dark, dark, dark], dice, lambda f: dice,
                    settings(freeze_frames=99, policy="void"))
    assert integrity.verdict == VOID
    assert any(e.kind == "obscured" for e in integrity.events)


def test_a_camera_that_drops_out_mid_hold_is_an_event_not_a_crash():
    frame, dice = scene()
    calls = {"n": 0}

    def grab():
        calls["n"] += 1
        if calls["n"] > 2:
            raise OSError("camera gone")
        return frame

    clock = Clock()
    integrity = TamperGuard(settings(freeze_frames=99)).watch(
        grab=grab, reread=lambda f: dice, sealed=dice, reference=frame,
        jpeg=b"x", sleep=clock.sleep, now=clock.time)
    assert any(e.kind == "capture" for e in integrity.events)


def test_an_event_is_recorded_once_however_long_it_lasts():
    # A hand held over the tray for two seconds is one reach, not forty.
    frame, dice = scene()
    frames = [frame] + [with_hand(frame)] * 20
    integrity = run(frames, dice, lambda f: dice, settings(hold_s=2.0))
    assert len([e for e in integrity.events if e.kind == "reach"]) == 1


# --- policy -----------------------------------------------------------------------


def test_the_guard_can_be_switched_off_entirely():
    frame, dice = scene()
    integrity = run([frame, with_hand(frame)], dice, lambda f: dice, settings(policy="off"))
    assert integrity.verdict == UNVERIFIED
    assert integrity.events == []


def test_a_strict_table_voids_even_an_unchanged_tray_that_was_touched():
    frame, dice = scene()
    integrity = run([frame, with_hand(frame), frame], dice, lambda f: dice,
                    settings(policy="void", void_on_touch=True))
    assert integrity.verdict == VOID


def test_the_dice_are_re_read_even_when_nothing_was_seen():
    # A die turned over entirely between two frames leaves no motion behind. The second
    # reading is what catches it, so it has to happen unconditionally.
    frame, dice = scene()
    turned = [Die("d6", 1, dice[0].box, 0.95)]
    integrity = run([frame] * 6, dice, lambda f: turned,
                    settings(policy="void", freeze_frames=99, always_recheck=True))
    assert integrity.verdict == VOID
