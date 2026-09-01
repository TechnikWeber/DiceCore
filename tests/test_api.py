"""
The HTTP surface, exercised against the simulator.

The point of these is the contract in docs/API.md: a game or a bot written against
`/api/v1/roll` today has to keep working. The setup endpoints are covered only where they
have bitten us — POST bodies in particular.
"""

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
