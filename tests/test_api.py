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


def test_the_page_itself_is_served(client):
    assert "DiceCore" in client.get("/").text
    assert client.get("/app.js").status_code == 200
    assert client.get("/style.css").status_code == 200
