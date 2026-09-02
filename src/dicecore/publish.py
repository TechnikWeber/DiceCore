"""
Sending a roll somewhere else: Discord, Avrae, or anything that speaks HTTP.

DiceCore reads physical dice. What a table usually wants next is for that number to appear
where the game already lives — in a Discord channel, or in the hands of the bot everyone is
using. This is the outbound half of the API: instead of somebody asking DiceCore for a roll,
DiceCore hands the roll over.

**How the Avrae bridge works, and what it cannot do.** Avrae rolls its own dice; there is no
way to make `!check athletics` use the die on your table, and anybody who tells you
otherwise is guessing. What *is* possible, and is verified against Avrae's own source: a
user variable can be written from outside Discord —

    POST https://api.avrae.io/customizations/uvars/<name>
    Authorization: <token from the Avrae dashboard>
    {"value": "..."}

— and an Avrae alias can read one with `get_uvar()`. So DiceCore writes the physical roll
into a variable, and a one-line alias in Discord reads it out. The player still types
something; the *number* comes off the table. See docs/AVRAE.md for the alias.

Written against `urllib` from the standard library on purpose: this has to work on the
ARMv6 Pi Zero that cannot install anything heavier.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from .dice import RollResult

#: The official Avrae API. Configurable because Avrae can be self-hosted.
AVRAE_API = "https://api.avrae.io"

#: Avrae refuses a blank uvar and caps the length; keep well under it.
UVAR_LIMIT = 8000

TIMEOUT_S = 8.0


@dataclass
class Attempt:
    """One delivery, kept so the setup page can show whether it worked."""

    target: str
    ok: bool
    detail: str = ""
    at: float = field(default_factory=time.time)

    def to_json(self) -> dict[str, Any]:
        return {"target": self.target, "ok": self.ok, "detail": self.detail, "at": self.at}


def roll_payload(result: RollResult) -> dict[str, Any]:
    """
    The roll as a small, flat object — the thing that ends up in a uvar or a webhook.

    Deliberately not the whole `RollResult`: a uvar has a size limit, and a Draconic alias
    reading this in Discord wants the four fields it will actually use, not the boxes the
    dice were found in.
    """
    return {
        "total": result.total,
        "notation": result.notation,
        "dice": [{"kind": d.kind, "value": d.value} for d in result.dice],
        "verdict": result.verdict,
        "usable": result.usable,
        "at": round(result.at, 1),
        "headline": (result.reading or {}).get("headline"),
        "mode": (result.reading or {}).get("mode"),
    }


def discord_message(result: RollResult, name: str = "DiceCore") -> dict[str, Any]:
    """A Discord webhook body. Plain text, because an embed is a lot of chrome for a number."""
    reading = result.reading or {}
    headline = reading.get("headline") or str(result.total)
    line = f"🎲 **{headline}** — {reading.get('detail') or result.notation}"
    if result.verdict == "void":
        line += "  ⚠️ *voided: the dice changed after they were read*"
    elif result.verdict == "disturbed":
        line += "  ⚠️ *the tray was disturbed*"
    return {"username": name, "content": line}


def _post(url: str, body: bytes, headers: dict[str, str]) -> tuple[bool, str]:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
            return True, f"{response.status}"
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:200].strip()
        return False, f"{exc.code} {exc.reason}{': ' + detail if detail else ''}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return False, str(exc)


def send_avrae(result: RollResult, token: str, uvar: str, base: str = AVRAE_API
               ) -> tuple[bool, str]:
    """
    Write the roll into an Avrae user variable.

    The token comes from the Avrae dashboard and is a credential: it can read and write that
    account's aliases and variables. It lives in DiceCore's config file, which is worth
    knowing before putting one on a machine other people can reach.
    """
    if not token:
        return False, "No Avrae token — copy one from avrae.io/dashboard."
    if not uvar:
        return False, "No variable name."
    value = json.dumps(roll_payload(result), separators=(",", ":"))
    if len(value) > UVAR_LIMIT:
        return False, f"Payload is {len(value)} characters, over Avrae's limit."
    return _post(
        f"{base.rstrip('/')}/customizations/uvars/{uvar}",
        json.dumps({"value": value}).encode(),
        {"Content-Type": "application/json", "Authorization": token},
    )


def send_discord(result: RollResult, webhook_url: str, name: str = "DiceCore"
                 ) -> tuple[bool, str]:
    if not webhook_url:
        return False, "No webhook URL."
    return _post(webhook_url, json.dumps(discord_message(result, name)).encode(),
                 {"Content-Type": "application/json"})


def send_webhook(result: RollResult, url: str) -> tuple[bool, str]:
    if not url:
        return False, "No URL."
    return _post(url, json.dumps(roll_payload(result)).encode(),
                 {"Content-Type": "application/json"})


class Publisher:
    """
    Hands finished rolls to whoever is configured to receive them.

    On a thread, always: a Discord webhook on a bad connection takes seconds, and nothing
    outside DiceCore may be allowed to slow down the reading of a die. A delivery that fails
    is recorded and forgotten — it is not retried, because a dice roll is only interesting
    for about ten seconds and a queue of stale ones is worse than none.
    """

    def __init__(self, settings: Any) -> None:
        self.settings = settings
        self.log: list[Attempt] = []
        self._lock = threading.Lock()

    def publish(self, result: RollResult, blocking: bool = False) -> list[Attempt]:
        config = self.settings.publish
        if not config.enabled:
            return []
        if config.only_usable and not result.usable:
            self._record(Attempt("skipped", True, f"verdict {result.verdict}"))
            return []
        if blocking:
            return self._send(result)
        threading.Thread(target=self._send, args=(result,), name="dicecore-publish",
                         daemon=True).start()
        return []

    def _send(self, result: RollResult) -> list[Attempt]:
        config = self.settings.publish
        attempts: list[Attempt] = []
        if config.avrae_enabled:
            ok, detail = send_avrae(result, config.avrae_token, config.avrae_uvar,
                                    config.avrae_api or AVRAE_API)
            attempts.append(Attempt("avrae", ok, detail))
        if config.discord_enabled:
            ok, detail = send_discord(result, config.discord_webhook, config.discord_name)
            attempts.append(Attempt("discord", ok, detail))
        if config.webhook_enabled:
            ok, detail = send_webhook(result, config.webhook_url)
            attempts.append(Attempt("webhook", ok, detail))
        for attempt in attempts:
            self._record(attempt)
        return attempts

    def _record(self, attempt: Attempt) -> None:
        with self._lock:
            self.log.append(attempt)
            del self.log[:-12]

    def describe(self) -> dict[str, Any]:
        config = self.settings.publish
        return {
            "enabled": config.enabled,
            "targets": {
                "avrae": {"on": config.avrae_enabled, "uvar": config.avrae_uvar,
                          "token": bool(config.avrae_token)},
                "discord": {"on": config.discord_enabled,
                            "webhook": bool(config.discord_webhook)},
                "webhook": {"on": config.webhook_enabled, "url": config.webhook_url},
            },
            "log": [a.to_json() for a in reversed(self.log)],
        }
