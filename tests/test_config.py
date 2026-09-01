import json

from dicecore.config import Settings


def test_round_trip_keeps_every_value(tmp_path):
    settings = Settings()
    settings.engine.expected_kinds = ["d6", "d20"]
    settings.tray.w = 0.5
    settings.save(tmp_path / "config.json")
    loaded, warnings = Settings.load(tmp_path / "config.json")
    assert not warnings
    assert loaded.engine.expected_kinds == ["d6", "d20"]
    assert loaded.tray.w == 0.5


def test_unknown_keys_survive_a_round_trip(tmp_path):
    # A config written by a newer version must not be destroyed by an older one.
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"capture": {"source": "v4l2"}, "somethingNew": {"a": 1}}))
    loaded, _ = Settings.load(path)
    assert loaded.capture.source == "v4l2"
    loaded.save(path)
    assert json.loads(path.read_text())["somethingNew"] == {"a": 1}


def test_unknown_fields_inside_a_known_section_are_ignored(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"capture": {"source": "v4l2", "gone": 1}}))
    loaded, _ = Settings.load(path)
    assert loaded.capture.source == "v4l2"


def test_a_broken_file_degrades_to_defaults_with_a_complaint(tmp_path):
    # A Pi that cannot parse its config still has to come up far enough to be fixed.
    path = tmp_path / "config.json"
    path.write_text("{ not json")
    loaded, warnings = Settings.load(path)
    assert loaded.capture.source == "folder"
    assert warnings and str(path) in warnings[0]


def test_a_missing_file_is_not_an_error(tmp_path):
    loaded, warnings = Settings.load(tmp_path / "nope.json")
    assert not warnings and loaded.server.port == 8099
