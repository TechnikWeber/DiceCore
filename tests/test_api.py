"""
The HTTP surface, exercised against the simulator.

The point of these is the contract in docs/API.md: a game or a bot written against
`/api/v1/roll` today has to keep working. The setup endpoints are covered only where they
have bitten us — POST bodies in particular.
"""

import time

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("cv2")

from fastapi.testclient import TestClient  # noqa: E402

from dicecore.config import Settings  # noqa: E402
from dicecore.server import create_app  # noqa: E402
from dicecore.synth import write_scenes  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DICECORE_STATE", str(tmp_path))
    frames = tmp_path / "frames"
    write_scenes(frames, count=4, kinds=("d6",))
    settings = Settings()
    settings.capture.source = "folder"
    settings.capture.folder = str(frames)
    # A hold window the suite can afford; the behaviour is identical at two seconds.
    settings.guard.hold_s = 0.2
    settings.guard.interval_s = 0.05
    with TestClient(create_app(settings)) as client:
        yield client


def test_health_says_who_it_is(client):
    body = client.get("/api/v1/health").json()
    assert body["ok"] and body["version"]


def test_a_roll_carries_everything_a_consumer_needs(client):
    body = client.get("/api/v1/roll").json()
    assert body["count"] >= 1
    assert body["total"] == sum(d["value"] for d in body["dice"])
    assert set(body) >= {"dice", "total", "count", "notation", "engine", "warnings"}
    assert set(body["dice"][0]) >= {"kind", "value", "box", "confidence"}


def test_a_roll_answers_before_the_tray_has_been_watched(client):
    # The default must not make anyone wait out the hold window: the number exists a
    # fraction of a second after the dice stop, and that is when it should arrive.
    started = time.perf_counter()
    body = client.get("/api/v1/roll").json()
    assert time.perf_counter() - started < 0.2
    assert body["verdict"] == "pending" and body["usable"] is True


def test_asking_for_the_verdict_up_front_waits_for_it(client):
    body = client.get("/api/v1/roll?verify=1").json()
    assert body["verdict"] == "clean"
    assert body["integrity"]["seal"].startswith("sha256:")


def test_the_verdict_lands_on_the_last_result_by_itself(client):
    rolled = client.get("/api/v1/roll").json()
    time.sleep(0.6)                                    # the hold window is 0.2s here
    settled = client.get("/api/v1/state").json()
    assert settled["at"] == rolled["at"]               # the same roll…
    assert settled["verdict"] == "clean"               # …now carrying its verdict


def test_a_caller_in_a_hurry_takes_the_number_and_the_verdict_separately(client):
    quick = client.get("/api/v1/roll?verify=0").json()
    assert quick["verdict"] == "pending" and quick["integrity"] is None
    verified = client.post("/api/v1/verify").json()
    assert verified["verdict"] == "clean"
    assert verified["total"] == quick["total"]


def test_verifying_before_anything_was_read_says_so(client):
    assert client.post("/api/v1/verify").status_code == 503


def test_a_die_turned_over_after_the_reading_voids_the_roll_end_to_end(tmp_path, monkeypatch):
    """
    The whole chain, staged through the real API: read a tray, swap a die under it, ask for
    the verdict. The `push` source is what makes this possible without a hand and a camera —
    and it is the same path a capture-only Pi agent uses.
    """
    import cv2

    from dicecore.synth import render_scene

    monkeypatch.setenv("DICECORE_STATE", str(tmp_path))
    settings = Settings()
    settings.capture.source = "push"
    settings.guard.policy = "void"
    settings.guard.hold_s = 0.2
    settings.guard.interval_s = 0.05

    def jpeg_of(spec):
        image, _ = render_scene(spec, seed=21, width=400, height=300, die_px=60)
        return cv2.imencode(".jpg", image)[1].tobytes()

    with TestClient(create_app(settings)) as client:
        client.post("/api/v1/frame", files={"image": jpeg_of([("d6", 4), ("d6", 2)])})
        honest = client.get("/api/v1/roll?verify=0").json()
        assert honest["total"] == 6 and honest["verdict"] == "pending"

        # Someone turns the 4 into a 6 while the tray is supposed to be untouched.
        client.post("/api/v1/frame", files={"image": jpeg_of([("d6", 6), ("d6", 2)])})

        verdict = client.post("/api/v1/verify").json()
        assert verdict["verdict"] == "void"
        assert verdict["usable"] is False
        assert any("now read" in e["detail"] for e in verdict["integrity"]["events"])


def test_state_returns_the_last_roll_without_capturing_again(client):
    rolled = client.get("/api/v1/roll").json()
    assert client.get("/api/v1/state").json()["at"] == rolled["at"]


def test_state_is_answerable_before_anything_has_been_read(client):
    assert client.get("/api/v1/state").json()["count"] == 0


def test_detect_reads_an_image_captured_somewhere_else(client, tmp_path):
    # This is the endpoint engine.mode=remote talks to — the seam that lets a Pi Zero
    # borrow a PC's engine.
    image = next(iter((tmp_path / "frames").glob("*.jpg")))
    body = client.post("/api/v1/detect", files={"image": image.read_bytes()}).json()
    assert body["count"] >= 1


def test_detect_rejects_something_that_is_not_an_image(client):
    assert client.post("/api/v1/detect", files={"image": b"nope"}).status_code == 400


def test_a_json_post_body_is_actually_read(client):
    # FastAPI resolves annotations against module globals, so `from __future__ import
    # annotations` in the server module silently turned every body into a missing query
    # parameter (422). This test is why that will not come back.
    created = client.post("/api/setup/sets", json={"name": "black d20s"})
    assert created.status_code == 200
    assert created.json()["id"] == "black-d20s"


def test_the_label_loop_stores_a_roll_and_takes_a_correction(client):
    set_id = client.post("/api/setup/sets", json={"name": "set"}).json()["id"]
    captured = client.post(f"/api/setup/sets/{set_id}/capture").json()
    sample_id = captured["sample"]["id"]
    assert client.get(f"/api/setup/sets/{set_id}/samples/{sample_id}.jpg").status_code == 200

    dice = [{"kind": "d6", "value": 6} for _ in captured["sample"]["dice"]]
    patched = client.patch(f"/api/setup/sets/{set_id}/samples/{sample_id}", json={"dice": dice})
    assert all(d["confirmed"] for d in patched.json()["dice"])
    assert client.get("/api/setup/sets").json()[0]["stats"]["confirmed_dice"] == len(dice)


def test_capturing_into_a_set_that_does_not_exist_is_a_404(client):
    assert client.post("/api/setup/sets/nope/capture").status_code == 404


def test_the_mode_list_is_part_of_the_versioned_api(client):
    # A consumer offering its own mode picker needs the same list DiceCore has.
    body = client.get("/api/v1/modes").json()
    assert body["active"] == "normal"
    ids = [m["id"] for m in body["modes"]]
    assert {"normal", "normal_extended", "rpg", "pool", "yahtzee", "custom"} <= set(ids)


def test_a_roll_carries_what_the_mode_made_of_it(client):
    body = client.get("/api/v1/roll").json()
    assert body["reading"]["mode"] == "normal"
    assert body["reading"]["headline"] == str(body["total"])


def test_one_roll_can_be_read_as_a_different_game_without_switching(client):
    # A bot counting successes and a screen showing a total can share one tray.
    body = client.get("/api/v1/roll?mode=pool").json()
    assert body["reading"]["mode"] == "pool"
    assert "success" in body["reading"]["headline"]
    # …and the configured mode is untouched.
    assert client.get("/api/v1/modes").json()["active"] == "normal"


def test_an_unknown_mode_is_refused_rather_than_guessed_at(client):
    assert client.get("/api/v1/roll?mode=nonsense").status_code == 400


def test_switching_mode_sticks(client):
    assert client.post("/api/setup/mode",
                       json={"mode": "yahtzee", "d10_style": "1-10"}).status_code == 200
    modes = client.get("/api/v1/modes").json()
    assert modes["active"] == "yahtzee" and modes["d10_style"] == "1-10"
    assert client.get("/api/v1/roll").json()["reading"]["mode"] == "yahtzee"


def test_a_mode_parameter_survives_a_save(client):
    client.post("/api/setup/mode", json={"mode": "pool", "params": {"threshold": 6}})
    body = client.get("/api/v1/roll").json()
    assert client.get("/api/v1/modes").json()["modes"][3]["params"] == {"threshold": 6}
    assert "success" in body["reading"]["headline"]


def test_the_d10_printing_style_changes_the_labels_offered(client):
    client.post("/api/setup/mode", json={"mode": "normal", "d10_style": "1-10"})
    kinds = client.get("/api/setup/options").json()["kinds"]
    d10 = next(k for k in kinds if k["id"] == "d10")
    assert d10["values"] == list(range(1, 11))


def test_the_setup_page_tells_the_ui_what_options_exist(client):
    body = client.get("/api/setup/options").json()
    assert any(m["id"] == "imx519" for m in body["csi_modules"])
    assert any(s["id"] == "folder" for s in body["sources"])
    assert any(k["id"] == "d20" and k["faces"] == 20 for k in body["kinds"])
    assert [p["id"] for p in body["policies"]] == ["off", "flag", "void"]


def test_settings_can_be_saved_and_come_back(client):
    settings = client.get("/api/setup/settings").json()
    settings["engine"]["expected_kinds"] = ["d6", "d20"]
    assert client.put("/api/setup/settings", json=settings).status_code == 200
    assert client.get("/api/setup/settings").json()["engine"]["expected_kinds"] == ["d6", "d20"]


def test_an_unknown_camera_module_is_refused_before_config_txt_is_touched(client):
    assert client.post("/api/setup/camera-module", json={"module": "nonsense"}).status_code == 400
    bad = client.post("/api/setup/camera-module",
                      json={"module": "custom", "overlay": "x\ndtoverlay=evil"})
    assert bad.status_code == 400


def test_both_front_doors_are_served(client):
    # The game screen is at the root because it is the one that stays on all evening.
    assert "play.js" in client.get("/").text
    assert "Setup" in client.get("/setup").text
    for asset in ("/app.js", "/play.js", "/style.css", "/play.css"):
        assert client.get(asset).status_code == 200, asset


def test_a_game_can_be_played_through_the_api(client):
    client.post("/api/v1/game/start",
                json={"mode": "yahtzee", "players": ["A", "B"], "params": {"chips": 1}})

    state = client.get("/api/v1/game").json()["game"]
    assert state["rules"]["rolls"] == 3 and state["rules"]["chips"] == 1
    assert state["current_player"] == "A"

    for expected in (1, 2, 3):
        client.get("/api/v1/roll?verify=0")
        assert client.get("/api/v1/game").json()["game"]["turn"]["rolls_used"] == expected

    turn = client.get("/api/v1/game").json()["game"]["turn"]
    assert turn["rolls_left"] == 0 and turn["can_spend_chip"]

    assert client.post("/api/v1/game/chip").json()["ok"]
    assert client.get("/api/v1/game").json()["game"]["turn"]["rolls_allowed"] == 4


def test_a_chip_is_refused_while_throws_remain(client):
    client.post("/api/v1/game/start",
                json={"mode": "yahtzee", "players": ["A"], "params": {"chips": 1}})
    client.get("/api/v1/roll?verify=0")
    answer = client.post("/api/v1/game/chip").json()
    assert not answer["ok"] and "no need" in answer["detail"].lower()


def test_booking_a_category_hands_the_tower_on(client):
    client.post("/api/v1/game/start", json={"mode": "yahtzee", "players": ["A", "B"]})
    client.get("/api/v1/roll?verify=0")
    booked = client.post("/api/v1/game/book", json={"category": "chance"}).json()
    assert booked["ok"] and booked["points"] > 0
    assert booked["game"]["current_player"] == "B"


def test_giving_a_category_up_has_to_be_meant(client):
    client.post("/api/v1/game/start", json={"mode": "yahtzee", "players": ["A"]})
    client.get("/api/v1/roll?verify=0")
    refused = client.post("/api/v1/game/book", json={"category": "kniffel"})
    assert refused.status_code == 400
    assert client.post("/api/v1/game/book",
                       json={"category": "kniffel", "cross_out": True}).json()["points"] == 0


def test_a_hold_can_be_corrected_from_the_browser(client):
    client.post("/api/v1/game/start", json={"mode": "yahtzee", "players": ["A"]})
    client.get("/api/v1/roll?verify=0")
    state = client.post("/api/v1/game/hold", json={"index": 0}).json()
    assert state["turn"]["dice"][0]["held"] is True


def test_the_buttons_are_reported_even_without_a_pi(client):
    buttons = client.get("/api/v1/game").json()["buttons"]
    assert "chip" in buttons and "next" in buttons


def test_a_zero_on_a_ten_sided_die_can_be_worth_nothing_instead_of_ten(client):
    # Standard is ten; some house rules count it as a plain zero.
    assert client.post("/api/setup/mode",
                       json={"mode": "normal", "d10_zero_counts_as_ten": False}).json()[
        "d10_zero_counts_as_ten"] is False
    assert client.get("/api/setup/settings").json()["mode"]["d10_zero_counts_as_ten"] is False


def test_nothing_is_running_until_a_game_is_started(client):
    # The screen showed numbers changing for a game nobody had started, which is what made
    # it impossible to understand. A game now has to be begun.
    assert client.get("/api/v1/game").json()["game"]["running"] is False


def test_starting_a_game_sets_everything_the_lobby_chose(client):
    started = client.post("/api/v1/game/start", json={
        "mode": "yahtzee", "players": ["Ada", "Bob", "Cy"],
        "colours": ["#5b8dff", "#3ecf8e", "#e0a94a"], "params": {"chips": 2},
    }).json()
    assert started["running"] and started["players"] == ["Ada", "Bob", "Cy"]
    assert started["colours"][1] == "#3ecf8e"
    assert started["chips"] == [2, 2, 2]
    assert client.get("/api/v1/modes").json()["active"] == "yahtzee"


def test_leaving_a_game_stops_the_reading(client):
    client.post("/api/v1/game/start", json={"mode": "yahtzee"})
    assert client.post("/api/v1/game/stop").json()["running"] is False


def test_a_game_started_without_names_gets_sensible_ones(client):
    # No keyboard at the table: every default has to be right on the first tap.
    started = client.post("/api/v1/game/start", json={"mode": "farkle"}).json()
    assert len(started["players"]) >= 1
    assert all(name for name in started["players"])
    assert len(started["colours"]) == len(started["players"])


def test_players_get_a_colour_each_even_when_none_were_chosen(client):
    started = client.post("/api/v1/game/start",
                          json={"mode": "yahtzee", "players": ["A", "B", "C", "D"]}).json()
    assert len(set(started["colours"])) == 4


def test_starting_an_unknown_game_is_refused(client):
    assert client.post("/api/v1/game/start", json={"mode": "nonsense"}).status_code == 400


def test_the_mode_list_says_what_kind_of_thing_each_mode_is(client):
    # The lobby groups by this: games to play, readers that only report, workshop tools.
    modes = {m["id"]: m["family"] for m in client.get("/api/v1/modes").json()["modes"]}
    assert modes["yahtzee"] == "board"
    assert modes["backgammon"] == "turns"
    assert modes["normal"] == "read"
    assert modes["fairness"] == "tool"


def test_the_panel_button_cannot_throw_a_kniffel_turn_away(client):
    client.post("/api/v1/game/start", json={"mode": "yahtzee", "players": ["A"]})
    client.get("/api/v1/roll?verify=0")
    refused = client.post("/api/v1/game/next")
    assert refused.status_code == 409 and "Book a category" in refused.json()["detail"]
    assert client.get("/api/v1/game").json()["game"]["turn"]["number"] == 1


def test_ending_a_turn_works_where_done_is_the_whole_story(client):
    client.post("/api/v1/game/start", json={"mode": "backgammon", "players": ["A", "B"]})
    client.get("/api/v1/roll?verify=0")
    after = client.post("/api/v1/game/next").json()
    assert after["turn"]["number"] == 2 and after["current_player"] == "B"


def test_the_extended_kniffel_sheet_is_offered_and_described(client):
    modes = [m["id"] for m in client.get("/api/v1/modes").json()["modes"]]
    assert "yahtzee_extreme" in modes
    client.post("/api/setup/mode", json={"mode": "yahtzee_extreme"})
    sheet = client.get("/api/v1/game").json()["game"]["sheet"]
    assert sheet["dice"] == 6 and sheet["bonus_at"] == 84
    assert "six_of_a_kind" in sheet["lower"]
    # The browser draws the card from this, so the labels have to come with it.
    assert sheet["labels"]["three_pairs"]


def test_farkle_is_played_by_setting_dice_aside_and_banking(client):
    client.post("/api/v1/game/start", json={"mode": "farkle", "players": ["A", "B"]})
    state = client.get("/api/v1/game").json()["game"]
    assert state["farkle"]["target"] == 10000 and state["turn"]["unlimited"]

    client.get("/api/v1/roll?verify=0")
    game = client.get("/api/v1/game").json()["game"]
    # Hold whichever dice actually score, then set them aside.
    scoring = [i for i, die in enumerate(game["turn"]["dice"]) if die["value"] in (1, 5)]
    for index in scoring:
        client.post("/api/v1/game/hold", json={"index": index})
    aside = client.post("/api/v1/game/aside").json()
    if scoring:
        assert aside["ok"] and aside["farkle"]["turn_points"] > 0
    else:
        assert not aside["ok"] and "score" in aside["detail"]


def test_setting_aside_a_die_that_scores_nothing_is_refused(client):
    client.post("/api/v1/game/start", json={"mode": "farkle", "players": ["A"]})
    client.get("/api/v1/roll?verify=0")
    answer = client.post("/api/v1/game/aside").json()      # nothing held at all
    assert not answer["ok"]


def test_a_game_without_a_board_refuses_to_bank(client):
    client.post("/api/setup/mode", json={"mode": "normal"})
    assert client.post("/api/v1/game/bank").status_code == 400


def test_chips_belong_to_the_player_for_the_whole_game(client):
    client.post("/api/v1/game/start",
                json={"mode": "yahtzee", "players": ["A", "B"], "params": {"chips": 2}})
    for _ in range(3):
        client.get("/api/v1/roll?verify=0")
    client.post("/api/v1/game/chip")
    assert client.get("/api/v1/game").json()["game"]["chips"] == [1, 2]


def test_the_page_itself_is_served(client):
    assert "DiceCore" in client.get("/setup").text


def test_saving_a_setting_cannot_take_a_running_game_away(client):
    # It could: a mode change in the setup page turned a Kniffel with points on the card
    # into an empty Farkle, mid-game, without a word.
    client.post("/api/v1/game/start", json={"mode": "yahtzee", "players": ["A", "B"]})
    client.get("/api/v1/roll?verify=0")
    client.post("/api/v1/game/book", json={"category": "chance"})
    before = client.get("/api/v1/game").json()["game"]

    settings = client.get("/api/setup/settings").json()
    settings["mode"]["active"] = "farkle"
    settings["panel"]["signals"]["beep_ms"] = 99
    client.put("/api/setup/settings", json=settings)

    after = client.get("/api/v1/game").json()["game"]
    assert after["mode"] == "yahtzee" and after["running"]
    assert after["cards"][0]["total"] == before["cards"][0]["total"]
    assert after["turn"]["number"] == before["turn"]["number"]


def test_the_new_mode_takes_effect_once_the_game_is_left(client):
    client.post("/api/v1/game/start", json={"mode": "yahtzee", "players": ["A"]})
    client.post("/api/setup/mode", json={"mode": "farkle"})
    assert client.get("/api/v1/game").json()["game"]["mode"] == "yahtzee"
    client.post("/api/v1/game/stop")
    client.post("/api/setup/mode", json={"mode": "farkle"})
    assert client.get("/api/v1/game").json()["game"]["mode"] == "farkle"


def test_the_page_can_see_what_is_installed_here(client):
    body = client.get("/api/setup/install").json()
    assert "train" in body["extras"] and "installed" in body["extras"]["train"]
    assert body["running"] is False


def test_only_a_known_extra_can_be_installed(client):
    # An endpoint that hands a user-supplied string to pip is remote code execution with a
    # friendly label on it. The request names a key; the key picks a constant.
    assert client.post("/api/setup/install", json={"extra": "train; rm -rf /"}).status_code == 400
    assert client.post("/api/setup/install", json={"extra": "requests"}).status_code == 400
    assert client.post("/api/setup/install", json={"extra": ""}).status_code == 400


def test_the_live_view_is_off_until_it_is_switched_on(client):
    # It is a camera. Leaving one streaming on an unauthenticated port is the room's
    # decision, not a default.
    refused = client.get("/api/v1/stream.mjpg")
    assert refused.status_code == 403 and "switched off" in refused.json()["detail"]
    assert client.get("/api/v1/health").json()["stream"] is False


def test_switching_the_live_view_on_is_reported(client):
    # The stream itself is not exercised here on purpose: reading an endless MJPEG response
    # inside the test client is a hang waiting to happen, and what this test can honestly
    # check is the switch. The stream is checked against a running server instead.
    settings = client.get("/api/setup/settings").json()
    settings["server"]["stream_enabled"] = True
    client.put("/api/setup/settings", json=settings)
    assert client.get("/api/v1/health").json()["stream"] is True
