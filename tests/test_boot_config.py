"""
config.txt is the one file that decides whether the Pi boots at all, so every rule about it
is pinned down here rather than discovered on a box that no longer comes up.
"""

import json

from dicecore.system.boot_config import (
    BootState,
    CsiModule,
    apply_camera_module,
    booted_state_changed,
    choose_tuning_file,
    explain_boot_config,
    has_autofocus_algorithm,
    module_by_id,
    module_id_for,
    parse_boot_config,
    strip_managed_block,
    system_tuning_file,
    valid_overlay_name,
)

PLAIN = "dtparam=audio=on\ncamera_auto_detect=1\ndtoverlay=vc4-kms-v3d\n"


def test_defaults_to_auto_detect_when_the_key_is_absent():
    assert parse_boot_config("dtparam=audio=on\n") == BootState(True, None)


def test_commented_lines_are_not_configuration():
    assert parse_boot_config("# dtoverlay=imx519\n# camera_auto_detect=0\n").overlay is None


def test_selecting_an_arducam_turns_auto_detect_off():
    out = apply_camera_module(PLAIN, "imx519")
    assert parse_boot_config(out) == BootState(False, "imx519")
    assert module_id_for(parse_boot_config(out)) == "imx519"


def test_competing_lines_are_commented_out_not_deleted():
    out = apply_camera_module(PLAIN, "imx519")
    assert "# camera_auto_detect=1  # (replaced by DiceCore)" in out
    # Unrelated overlays are none of our business and must survive untouched.
    assert "\ndtoverlay=vc4-kms-v3d\n" in out


def test_applying_twice_does_not_stack_blocks():
    once = apply_camera_module(PLAIN, "imx519")
    assert apply_camera_module(once, "imx519") == once


def test_switching_back_to_auto_restores_auto_detect():
    out = apply_camera_module(apply_camera_module(PLAIN, "imx519"), None)
    assert parse_boot_config(out) == BootState(True, None)
    assert module_id_for(parse_boot_config(out)) == "auto"


def test_the_block_can_be_removed_again():
    out = apply_camera_module(PLAIN, "imx519")
    assert "DiceCore camera module" not in strip_managed_block(out)


def test_a_custom_overlay_cannot_inject_a_second_directive():
    assert valid_overlay_name("imx519")
    assert valid_overlay_name("imx519,vcm")
    assert not valid_overlay_name("imx519\ndtoverlay=evil")
    assert not valid_overlay_name("../../etc/passwd")
    assert not valid_overlay_name("")


def test_reboot_is_due_only_when_the_effective_config_changed():
    booted = BootState(True, None)
    assert not booted_state_changed(booted, BootState(True, None))
    assert booted_state_changed(booted, BootState(False, "imx519"))


def test_the_imx519_ships_a_tuning_file_because_the_stock_one_has_no_autofocus():
    module = module_by_id("imx519")
    assert module is not None and module.tuning_file and module.focus


def test_no_camera_is_explained_differently_depending_on_why():
    forced = explain_boot_config(BootState(False, "imx519"), 0)
    assert forced is not None and "imx519" in forced
    assert "auto_detect" in (explain_boot_config(BootState(True, None), 0) or "").replace(
        "camera_auto_detect", "auto_detect")
    off = explain_boot_config(BootState(False, None), 0)
    assert off is not None and "never looks" in off
    # A working camera needs no explanation at all.
    assert explain_boot_config(BootState(True, None), 1) is None


# --- tuning files ---------------------------------------------------------------
#
# A tuning file that is not on disk does not fall back to the stock one: libcamera refuses
# to register the sensor and rpicam-still answers "no cameras available". Selecting the
# Arducam then looks exactly like a ribbon cable fault, so these pin down that we never
# write a path we do not have.


def _module(tmp_path, name="imx519-af.json"):
    return CsiModule("imx519", "Arducam", "imx519", "note", tuning_file=str(tmp_path / name),
                     focus=True)


def test_a_module_without_a_tuning_file_asks_for_none(tmp_path):
    assert choose_tuning_file(module_by_id("auto")) == ("", None)


def test_an_installed_tuning_file_is_used(tmp_path):
    module = _module(tmp_path)
    (tmp_path / "imx519-af.json").write_text("{}")
    assert choose_tuning_file(module) == (module.tuning_file, None)


def test_a_missing_tuning_file_is_never_written_into_the_settings(tmp_path):
    chosen, note = choose_tuning_file(_module(tmp_path))
    assert chosen == ""
    assert note and "not installed" in note and "lens" in note


def test_the_complaint_says_so_when_libcameras_own_tuning_already_focuses(tmp_path, monkeypatch):
    ipa = tmp_path / "vc4"
    ipa.mkdir()
    (ipa / "imx519.json").write_text(json.dumps({"algorithms": [{"rpi.af": {}}]}))
    monkeypatch.setattr("dicecore.system.boot_config.IPA_DIRS", (str(ipa),))
    chosen, note = choose_tuning_file(_module(tmp_path))
    assert chosen == ""
    assert note and "autofocus works" in note


def test_the_system_tuning_file_is_found_by_sensor_name(tmp_path):
    (tmp_path / "imx519.json").write_text("{}")
    assert system_tuning_file("imx519,vcm", (str(tmp_path),)) == tmp_path / "imx519.json"
    assert system_tuning_file("imx708", (str(tmp_path),)) is None
    assert system_tuning_file(None, (str(tmp_path),)) is None


def test_autofocus_is_decided_by_the_rpi_af_block(tmp_path):
    plain, af = tmp_path / "a.json", tmp_path / "b.json"
    plain.write_text('{"algorithms": [{"rpi.agc": {}}]}')
    af.write_text('{"algorithms": [{"rpi.af": {}}]}')
    assert not has_autofocus_algorithm(plain)
    assert has_autofocus_algorithm(af)
    assert not has_autofocus_algorithm(None)
