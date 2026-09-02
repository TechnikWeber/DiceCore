"""
Sending rolls out.

The delivery itself is one `urllib` call and is not worth mocking a network for; what these
check is the shape of what goes out, the refusal to send when something is missing, and the
one rule that matters at a table — a voided roll does not leave the building.
"""

import json

import pytest

from dicecore.config import Settings
from dicecore.dice import Box, Die, RollResult
from dicecore.publish import (
    AVRAE_API,
    Publisher,
    discord_message,
    roll_payload,
    send_avrae,
    send_discord,
    send_webhook,
)


def roll(verdict: str = "clean") -> RollResult:
    result = RollResult(
        dice=[Die("d20", 17, Box(0, 0, 60, 60), 0.97), Die("d6", 4, Box(80, 0, 50, 50), 0.99)],
        engine="model", verdict=verdict)
    result.reading = {"headline": "21", "detail": "4, 17", "mode": "rpg"}
    return result


# --- what goes out ----------------------------------------------------------------


def test_the_payload_is_small_and_flat():
    # It has to fit in an Avrae variable and be read by a Draconic alias, which wants the
    # fields it will use rather than the boxes the dice were found in.
    payload = roll_payload(roll())
    assert payload["total"] == 21 and payload["headline"] == "21"
    assert payload["dice"] == [{"kind": "d20", "value": 17}, {"kind": "d6", "value": 4}]
    assert payload["usable"] is True and payload["verdict"] == "clean"
    assert "box" not in json.dumps(payload)


def test_the_payload_is_json_a_draconic_alias_can_load():
    text = json.dumps(roll_payload(roll()))
    assert json.loads(text)["dice"][0]["kind"] == "d20"


def test_a_discord_message_says_the_number_first():
    content = discord_message(roll())["content"]
    assert "**21**" in content and "4, 17" in content


def test_a_disturbed_or_voided_roll_says_so_in_the_message():
    assert "voided" in discord_message(roll("void"))["content"]
    assert "disturbed" in discord_message(roll("disturbed"))["content"]


# --- refusing rather than pretending ----------------------------------------------


def test_nothing_is_sent_without_the_thing_it_needs():
    assert send_avrae(roll(), "", "dicecore")[0] is False
    assert "token" in send_avrae(roll(), "", "dicecore")[1]
    assert send_avrae(roll(), "tok", "")[0] is False
    assert send_discord(roll(), "")[0] is False
    assert send_webhook(roll(), "")[0] is False


def test_the_avrae_endpoint_is_the_one_avrae_documents_in_its_own_source():
    # POST /customizations/uvars/<name> with an Authorization header and {"value": …}.
    assert AVRAE_API == "https://api.avrae.io"


# --- the publisher ----------------------------------------------------------------


def settings(**overrides) -> Settings:
    s = Settings()
    s.publish.enabled = True
    for key, value in overrides.items():
        setattr(s.publish, key, value)
    return s


def test_sending_is_off_until_it_is_switched_on():
    s = Settings()
    assert not s.publish.enabled
    assert Publisher(s).publish(roll(), blocking=True) == []


def test_a_voided_roll_does_not_leave_the_building():
    # The one rule that matters: a number that was interfered with is exactly the one you do
    # not want turning up in somebody's game.
    publisher = Publisher(settings(webhook_enabled=True, webhook_url="http://127.0.0.1:1/x"))
    assert publisher.publish(roll("void"), blocking=True) == []
    assert publisher.log[-1].target == "skipped"


def test_a_voided_roll_goes_out_if_the_table_asked_for_that():
    publisher = Publisher(settings(only_usable=False, webhook_enabled=True,
                                   webhook_url="http://127.0.0.1:1/x"))
    attempts = publisher.publish(roll("void"), blocking=True)
    assert [a.target for a in attempts] == ["webhook"]


def test_a_delivery_that_fails_is_recorded_and_not_retried():
    # A dice roll is interesting for about ten seconds; a queue of stale ones is worse than
    # none. Port 1 refuses instantly, which is the point.
    publisher = Publisher(settings(webhook_enabled=True, webhook_url="http://127.0.0.1:1/x"))
    attempts = publisher.publish(roll(), blocking=True)
    assert len(attempts) == 1 and attempts[0].ok is False
    assert publisher.log[-1].ok is False


def test_every_switched_on_target_is_tried_even_if_one_fails():
    publisher = Publisher(settings(
        avrae_enabled=True, avrae_token="x", avrae_api="http://127.0.0.1:1",
        discord_enabled=True, discord_webhook="http://127.0.0.1:1/hook",
        webhook_enabled=True, webhook_url="http://127.0.0.1:1/x"))
    assert [a.target for a in publisher.publish(roll(), blocking=True)] == \
        ["avrae", "discord", "webhook"]


def test_the_log_stays_short():
    publisher = Publisher(settings(webhook_enabled=True, webhook_url="http://127.0.0.1:1/x"))
    for _ in range(20):
        publisher.publish(roll(), blocking=True)
    assert len(publisher.log) <= 12


def test_what_is_described_never_includes_the_credentials():
    # The page has to say whether a token is set, and must not hand it back out.
    publisher = Publisher(settings(avrae_enabled=True, avrae_token="secret-token",
                                    discord_webhook="https://discord.com/api/webhooks/x"))
    described = json.dumps(publisher.describe())
    assert "secret-token" not in described
    assert "discord.com/api/webhooks/x" not in described
    assert publisher.describe()["targets"]["avrae"]["token"] is True


@pytest.mark.parametrize("size", [9000])
def test_a_payload_too_large_for_a_variable_is_refused(size):
    big = RollResult(dice=[Die("d6", 3, Box(0, 0, 10, 10), 0.9) for _ in range(size // 30)])
    ok, detail = send_avrae(big, "token", "dicecore")
    assert not ok and "limit" in detail
