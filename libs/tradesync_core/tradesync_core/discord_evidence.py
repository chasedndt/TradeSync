"""Turn a Discord message from the ChaseOS agent channels into quarantine material.

The Hermes fleet and the Strike Zone alerts post to a private Discord server.
Those posts are the operator's existing workflow, and moving them into Market
Command means *reading* them into quarantine with provenance, never treating
them as signals. This module is the pure mapping: a raw Discord message object
becomes one bounded, authority-free submission for ``POST /state/quarantine``.

Rules:

- The payload carries who said it, where, and when. It never carries trust,
  tier, direction weight or any field ``quarantine.FORBIDDEN_FIELDS`` names.
- Content is bounded. A message longer than the bound is truncated and says so,
  rather than being refused outright, because a long agent report is still
  worth seeing.
- The agent name is the channel's configured label first, the author second.
  A channel is a stable identity; a bot's display name is not.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "discord_message_v1"
SOURCE = "discord"
MAX_CONTENT_CHARS = 8_000
MAX_EMBEDS = 5
MAX_ATTACHMENTS = 10
TRUNCATED_NOTE = "[truncated by discord_evidence: message exceeded the content bound]"

_SNOWFLAKE = re.compile(r"^\d{15,22}$")


@dataclass(frozen=True)
class ChannelSpec:
    """One channel the reader watches, from the operator's configuration."""

    channel_id: str
    label: str  # the agent or stream name the operator gave it
    kind: str = "agent"  # agent | alerts | operator


class ChannelConfigError(ValueError):
    pass


def parse_channel_config(raw: str) -> list[ChannelSpec]:
    """``label=channel_id[:kind],...`` -> specs. Refuses malformed entries.

    Refusing beats guessing: a wrong channel id silently reads the wrong room.
    """
    specs: list[ChannelSpec] = []
    for entry in (part.strip() for part in raw.split(",") if part.strip()):
        if "=" not in entry:
            raise ChannelConfigError(f"'{entry}' is not label=channel_id")
        label, rest = entry.split("=", 1)
        channel_id, _, kind = rest.partition(":")
        label, channel_id, kind = label.strip(), channel_id.strip(), (kind.strip() or "agent")
        if not label:
            raise ChannelConfigError(f"'{entry}' has an empty label")
        if not _SNOWFLAKE.match(channel_id):
            raise ChannelConfigError(f"'{channel_id}' is not a Discord channel id")
        if kind not in {"agent", "alerts", "operator"}:
            raise ChannelConfigError(f"'{kind}' is not a channel kind (agent|alerts|operator)")
        specs.append(ChannelSpec(channel_id, label, kind))
    if len({s.channel_id for s in specs}) != len(specs):
        raise ChannelConfigError("a channel id appears twice")
    return specs


def message_observed_at_ms(message: Mapping[str, Any]) -> int | None:
    """Discord's ISO-8601 timestamp as epoch milliseconds."""
    raw = message.get("timestamp")
    if not isinstance(raw, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def _embed(e: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "title": str(e.get("title") or "")[:512],
        "description": str(e.get("description") or "")[:2_000],
        "url": str(e.get("url") or "")[:512],
        "fields": [
            {"name": str(f.get("name") or "")[:256], "value": str(f.get("value") or "")[:1_024]}
            for f in (e.get("fields") or [])[:10]
            if isinstance(f, Mapping)
        ],
    }


def _attachment(a: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "filename": str(a.get("filename") or "")[:256],
        "content_type": str(a.get("content_type") or "")[:128],
        "size": a.get("size") if isinstance(a.get("size"), int) else None,
        "url": str(a.get("url") or "")[:1_024],
    }


def to_submission(message: Mapping[str, Any], channel: ChannelSpec) -> dict[str, Any]:
    """One Discord message -> ``{"source", "payload", "observed_at_ms"}``."""
    author = message.get("author") or {}
    content = str(message.get("content") or "")
    truncated = len(content) > MAX_CONTENT_CHARS
    if truncated:
        content = content[:MAX_CONTENT_CHARS] + "\n" + TRUNCATED_NOTE
    embeds: Sequence[Any] = message.get("embeds") or []
    attachments: Sequence[Any] = message.get("attachments") or []
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "discord_message",
        "agent": channel.label,
        "channel_kind": channel.kind,
        "channel_id": channel.channel_id,
        "message_id": str(message.get("id") or ""),
        "author": {
            "id": str(author.get("id") or ""),
            "name": str(author.get("username") or author.get("global_name") or "")[:128],
            "bot": bool(author.get("bot", False)),
        },
        "content": content,
        "content_truncated": truncated,
        "embeds": [_embed(e) for e in embeds[:MAX_EMBEDS] if isinstance(e, Mapping)],
        "attachments": [_attachment(a) for a in attachments[:MAX_ATTACHMENTS] if isinstance(a, Mapping)],
        "posted_at": message.get("timestamp"),
        "edited_at": message.get("edited_timestamp"),
    }
    return {"source": SOURCE, "payload": payload, "observed_at_ms": message_observed_at_ms(message)}


def newest_id(messages: Sequence[Mapping[str, Any]]) -> str | None:
    """The largest snowflake in a batch; snowflakes are time-ordered."""
    ids = [int(m["id"]) for m in messages if _SNOWFLAKE.match(str(m.get("id") or ""))]
    return str(max(ids)) if ids else None
