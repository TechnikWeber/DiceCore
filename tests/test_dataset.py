import pytest

from dicecore.dataset import DatasetStore
from dicecore.dice import Box, Die, RollResult
from dicecore.training.data import readiness


@pytest.fixture
def store(tmp_path) -> DatasetStore:
    return DatasetStore(tmp_path)


def result() -> RollResult:
    # The d20 is unread — no value and no confidence — which is what the classic engine
    # produces for a numeral die and what the label loop exists to fix.
    return RollResult(dice=[Die("d20", 0, Box(0, 0, 30, 30), confidence=0.0),
                            Die("d6", 4, Box(40, 0, 30, 30), confidence=0.99)],
                      engine="classic")


def test_two_sets_with_the_same_name_do_not_merge(store):
    first = store.create_set("d20s")
    second = store.create_set("d20s")
    assert first.id != second.id
    assert {s.id for s in store.list_sets()} == {first.id, second.id}


def test_a_stored_roll_starts_unconfirmed_but_pre_filled(store):
    record = store.create_set("set")
    sample = store.add_sample(record.id, b"jpeg", result())
    assert [d.confirmed for d in sample.dice] == [False, False]
    # The engine's guess is kept so the page opens pre-filled and only wrong dice are
    # touched — and a die it could not read is stored as "no guess", not as a zero.
    assert [d.predicted for d in sample.dice] == [None, 4]


def test_correcting_a_die_keeps_what_the_engine_had_said(store):
    record = store.create_set("set")
    sample = store.add_sample(record.id, b"jpeg", result())
    store.update_sample(record.id, sample.id,
                        [{"kind": "d20", "value": 17}, {"kind": "d6", "value": 4}])
    stored = store.get_sample(record.id, sample.id)
    assert [d.value for d in stored.dice] == [17, 4]
    assert [d.predicted for d in stored.dice] == [None, 4]
    assert all(d.confirmed for d in stored.dice)


def test_an_impossible_value_is_refused(store):
    record = store.create_set("set")
    sample = store.add_sample(record.id, b"jpeg", result())
    with pytest.raises(ValueError):
        store.update_sample(record.id, sample.id, [{"kind": "d6", "value": 14}])


def test_stats_count_only_confirmed_dice_and_measure_the_engine(store):
    record = store.create_set("set")
    sample = store.add_sample(record.id, b"jpeg", result())
    assert store.stats(record.id)["confirmed_dice"] == 0
    store.update_sample(record.id, sample.id,
                        [{"kind": "d20", "value": 17}, {"kind": "d6", "value": 4}])
    stats = store.stats(record.id)
    assert stats["confirmed_dice"] == 2
    assert stats["classes"] == {"d20:17": 1, "d6:4": 1}
    assert stats["engine_agreement"] == 0.5  # it had the d6 right and the d20 wrong


def test_readiness_refuses_to_train_on_almost_nothing(store):
    record = store.create_set("set")
    state = readiness(store, record.id)
    assert not state.ready and state.reasons


def test_deleting_a_sample_removes_both_the_frame_and_the_label(store):
    record = store.create_set("set")
    sample = store.add_sample(record.id, b"jpeg", result())
    assert store.frame_path(record.id, sample.id).is_file()
    store.delete_sample(record.id, sample.id)
    assert not store.frame_path(record.id, sample.id).is_file()
    assert list(store.iter_samples(record.id)) == []


def test_an_unreadable_label_does_not_stop_a_training_run(store):
    record = store.create_set("set")
    store.add_sample(record.id, b"jpeg", result())
    (store.set_dir(record.id) / "labels" / "broken.json").write_text("{ not json")
    assert len(list(store.iter_samples(record.id))) == 1


def test_a_ten_sided_die_printed_one_to_ten_can_be_labelled(tmp_path):
    # The printing style is a setting, and a setting that makes its own labels illegal is
    # worse than no setting: it made the whole 1–10 option useless for training.
    store = DatasetStore(tmp_path, d10_style="1-10")
    record = store.create_set("set")
    sample = store.add_sample(record.id, b"jpeg", RollResult(
        dice=[Die("d10", 0, Box(0, 0, 30, 30), confidence=0.0)]))
    store.update_sample(record.id, sample.id, [{"kind": "d10", "value": 10}])
    assert store.get_sample(record.id, sample.id).dice[0].value == 10


def test_a_zero_is_refused_on_a_die_printed_one_to_ten(tmp_path):
    store = DatasetStore(tmp_path, d10_style="1-10")
    record = store.create_set("set")
    sample = store.add_sample(record.id, b"jpeg", RollResult(
        dice=[Die("d10", 1, Box(0, 0, 30, 30), confidence=0.9)]))
    with pytest.raises(ValueError, match="printed 1-10"):
        store.update_sample(record.id, sample.id, [{"kind": "d10", "value": 0}])


# --- carrying a set between machines ----------------------------------------------


def sample_set(tmp_path, name="his d20s", values=(3, 17, 20)):
    import cv2

    from dicecore.synth import render_scene

    store = DatasetStore(tmp_path)
    record = store.create_set(name, "his table, his lamp")
    for value in values:
        image, _ = render_scene([("d20", value)], seed=value, width=300, height=240, die_px=90)
        sample = store.add_sample(record.id, cv2.imencode(".jpg", image)[1].tobytes(),
                                  RollResult(dice=[Die("d20", 0, Box(100, 70, 100, 100),
                                                       confidence=0.0)]))
        store.update_sample(record.id, sample.id, [{"kind": "d20", "value": value}])
    return store, record


def test_a_set_travels_as_a_plain_zip(tmp_path):
    pytest.importorskip("cv2")
    from dicecore.dataset import transfer

    store, record = sample_set(tmp_path)
    blob = transfer.export_set(store, record.id)
    manifest = transfer.describe(blob)
    assert manifest["frames"] == 3 and manifest["confirmed"] == 3
    assert manifest["set"]["name"] == "his d20s"

    # A zip of exactly what is on disk, so anything can read it.
    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        names = archive.namelist()
    assert any(n.startswith("frames/") and n.endswith(".jpg") for n in names)
    assert any(n.startswith("labels/") and n.endswith(".json") for n in names)


def test_an_imported_set_is_always_a_new_one(tmp_path):
    # Two people's dice under two people's lamps are two sets; quietly mixing them is how a
    # model ends up learning the average of two setups and being worse at both.
    pytest.importorskip("cv2")
    from dicecore.dataset import transfer

    store, record = sample_set(tmp_path)
    blob = transfer.export_set(store, record.id)
    result = transfer.import_set(store, blob)
    assert result["set"]["id"] != record.id
    assert result["frames"] == 3 and result["labels"] == 3
    assert len(store.list_sets()) == 2

    # And the labels came through, not just the pictures.
    imported = list(store.iter_samples(result["set"]["id"]))
    assert sorted(d.value for s in imported for d in s.dice) == [3, 17, 20]


def test_a_zip_that_is_not_a_set_is_refused(tmp_path):
    import io
    import zipfile

    from dicecore.dataset import transfer

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("holiday.jpg", b"not a dataset")
    with pytest.raises(ValueError, match="not a DiceCore set"):
        transfer.import_set(DatasetStore(tmp_path), buffer.getvalue())


def test_an_archive_cannot_write_outside_the_set(tmp_path):
    # "../../etc/cron.d/x" is a real attack and a zip is exactly where it comes from.
    import io
    import zipfile

    from dicecore.dataset import transfer

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(transfer.MANIFEST,
                         '{"version": 1, "set": {"name": "evil"}, "frames": 0}')
        archive.writestr("frames/../../../escaped.jpg", b"x")
    store = DatasetStore(tmp_path)
    result = transfer.import_set(store, buffer.getvalue())
    assert not (tmp_path.parent / "escaped.jpg").exists()
    assert (store.set_dir(result["set"]["id"]) / "frames" / "escaped.jpg").is_file()
