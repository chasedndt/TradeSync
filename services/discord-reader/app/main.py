"""Read the ChaseOS agent channels on Discord into TradeSync quarantine.

A small, read-only bridge. It polls each configured channel through Discord's
REST API with a bot token, maps every new message to a quarantine submission
(``tradesync_core.discord_evidence``), and posts it to ``state-api``. It never
writes to Discord, never talks to a model, and never touches the feature
catalog: what it reads lands as untrusted material with provenance, and stays
there until a human or a measured evidence card says otherwise.

Off unless both ``DISCORD_BOT_TOKEN`` and ``DISCORD_READER_CHANNELS`` are set.
The token is read once, sent only in the Authorization header to
discord.com, and never logged.

Cursor: the newest message id seen per channel, kept in Redis so a restart
resumes where it stopped. On first sight of a channel the reader starts from
"now" rather than replaying history, because quarantine's staleness bound
would refuse old messages anyway and a backfill is a separate, deliberate
import.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

import httpx
import redis.asyncio as redis_lib

from tradesync_core.discord_evidence import (
    ChannelConfigError,
    ChannelSpec,
    newest_id,
    parse_channel_config,
    to_submission,
)

DISCORD_API = "https://discord.com/api/v10"
STATE_API_URL = os.getenv("STATE_API_URL", "http://state-api:8000").rstrip("/")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
POLL_SECONDS = max(10, int(os.getenv("DISCORD_POLL_SECONDS", "30")))
PAGE_LIMIT = 100
CURSOR_KEY = "discord_reader:cursor:{channel_id}"
# Discord's per-route bucket is ~5 requests per 5 s for channel messages; a
# spacing of one second per channel keeps a ten-channel poll well inside it.
REQUEST_SPACING_S = 1.0
# A channel the bot cannot read (wrong id, not invited, no permission) is not
# retried every pass: that is a configuration fact, logged once and re-checked
# on a long interval so a fix is picked up without a restart.
FORBIDDEN_HOLD_S = 30 * 60
_held_until: dict[str, float] = {}


def configured() -> tuple[str, list[ChannelSpec]] | None:
    token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
    raw = os.getenv("DISCORD_READER_CHANNELS", "").strip()
    if not token or not raw:
        return None
    return token, parse_channel_config(raw)


async def fetch_new_messages(
    client: httpx.AsyncClient, token: str, channel: ChannelSpec, after: str | None
) -> list[dict[str, Any]] | None:
    """Messages newer than ``after``, oldest first; None if the read failed.

    With no cursor only the newest message is fetched, to establish "now".
    """
    params: dict[str, Any] = {"limit": PAGE_LIMIT if after else 1}
    if after:
        params["after"] = after
    try:
        response = await client.get(
            f"{DISCORD_API}/channels/{channel.channel_id}/messages",
            params=params,
            headers={"Authorization": f"Bot {token}", "User-Agent": "TradeSync discord-reader (private)"},
            timeout=15.0,
        )
    except httpx.HTTPError as exc:
        print(f"[DiscordReader] {channel.label}: request failed: {type(exc).__name__}")
        return None
    if response.status_code == 429:
        retry = response.headers.get("Retry-After", "5")
        print(f"[DiscordReader] {channel.label}: rate limited, retry after {retry}s")
        return None
    if response.status_code in (401, 403, 404):
        # Wrong token, missing permission, or wrong channel id: say which,
        # never retry into a wall. The token itself is not printed.
        _held_until[channel.channel_id] = time.time() + FORBIDDEN_HOLD_S
        print(
            f"[DiscordReader] {channel.label}: HTTP {response.status_code} "
            f"(token, permission or channel id); held for {FORBIDDEN_HOLD_S // 60} min"
        )
        return None
    if response.status_code >= 400:
        print(f"[DiscordReader] {channel.label}: HTTP {response.status_code}")
        return None
    try:
        data = response.json()
    except ValueError:
        return None
    if not isinstance(data, list):
        return None
    # Discord returns newest first; submit oldest first so cursors move monotonically.
    return sorted((m for m in data if isinstance(m, dict)), key=lambda m: int(m.get("id", 0)))


async def submit(client: httpx.AsyncClient, submission: dict[str, Any]) -> bool:
    try:
        response = await client.post(f"{STATE_API_URL}/state/quarantine", json=submission, timeout=15.0)
        response.raise_for_status()
        return bool(response.json().get("accepted"))
    except (httpx.HTTPError, ValueError) as exc:
        print(f"[DiscordReader] quarantine submit failed: {type(exc).__name__}")
        raise


async def poll_channel(
    client: httpx.AsyncClient, r, token: str, channel: ChannelSpec
) -> dict[str, int]:
    key = CURSOR_KEY.format(channel_id=channel.channel_id)
    cursor = await r.get(key)
    cursor = cursor.decode() if isinstance(cursor, bytes) else cursor
    messages = await fetch_new_messages(client, token, channel, cursor)
    if messages is None:
        return {"read": 0, "accepted": 0, "refused": 0}
    if cursor is None:
        # First sight: record "now" and read forward from here.
        latest = newest_id(messages)
        if latest:
            await r.set(key, latest)
        print(f"[DiscordReader] {channel.label}: cursor established at {latest}")
        return {"read": 0, "accepted": 0, "refused": 0}

    accepted = refused = 0
    for message in messages:
        try:
            ok = await submit(client, to_submission(message, channel))
        except Exception:
            # Leave the cursor where it was so this message is retried.
            break
        accepted += int(ok)
        refused += int(not ok)
        await r.set(key, str(message["id"]))
    return {"read": len(messages), "accepted": accepted, "refused": refused}


async def run_forever() -> None:
    try:
        cfg = configured()
    except ChannelConfigError as exc:
        print(f"[DiscordReader] refusing to start: {exc}")
        return
    if cfg is None:
        print("[DiscordReader] not configured (DISCORD_BOT_TOKEN and DISCORD_READER_CHANNELS unset); idle")
        while True:
            await asyncio.sleep(3600)
    token, channels = cfg
    print(f"[DiscordReader] watching {len(channels)} channel(s): {', '.join(c.label for c in channels)}")
    r = redis_lib.from_url(REDIS_URL)
    async with httpx.AsyncClient() as client:
        while True:
            started = time.time()
            totals = {"read": 0, "accepted": 0, "refused": 0}
            for channel in channels:
                if _held_until.get(channel.channel_id, 0) > time.time():
                    continue
                stats = await poll_channel(client, r, token, channel)
                for k in totals:
                    totals[k] += stats[k]
                await asyncio.sleep(REQUEST_SPACING_S)
            if totals["read"]:
                print(f"[DiscordReader] pass: read {totals['read']}, accepted {totals['accepted']}, refused {totals['refused']}")
            await asyncio.sleep(max(1.0, POLL_SECONDS - (time.time() - started)))


if __name__ == "__main__":
    asyncio.run(run_forever())
