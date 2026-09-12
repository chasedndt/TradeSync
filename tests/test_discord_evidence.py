"""A Discord message becomes bounded, authority-free quarantine material."""

from __future__ import annotations

import pytest

from tradesync_core.discord_evidence import (
    MAX_CONTENT_CHARS,
    TRUNCATED_NOTE,
    ChannelConfigError,
    ChannelSpec,
    message_observed_at_ms,
    newest_id,
    parse_channel_config,
    to_submission,
)
from tradesync_core.quarantine import FORBIDDEN_FIELDS, evaluate_submission

CH = ChannelSpec("123456789012345678", "hermes-macro", "agent")


def msg(**over):
    base = {
        "id": "1420000000000000001",
        "channel_id": CH.channel_id,
        "author": {"id": "99", "username": "Hermes Macro", "bot": True},
        "content": "BTC funding flipped negative overnight; watching 77k.",
        "timestamp": "2026-09-12T18:30:00.123000+00:00",
        "edited_timestamp": None,
        "embeds": [{"title": "Macro brief", "description": "CPI Thursday", "fields": [{"name": "DXY", "value": "up"}]}],
        "attachments": [{"filename": "chart.png", "content_type": "image/png", "size": 1234, "url": "https://cdn.discordapp.com/x/chart.png"}],
    }
    base.update(over)
    return base


def test_channel_config_parses_labels_ids_and_kinds_and_refuses_bad_entries() -> None:
    specs = parse_channel_config("hermes-macro=123456789012345678, alerts=223456789012345678:alerts")
    assert specs[0] == CH and specs[1].kind == "alerts"
    for bad in ("nolabel", "x=notanid", "x=123456789012345678:weird", "a=123456789012345678,b=123456789012345678"):
        with pytest.raises(ChannelConfigError):
            parse_channel_config(bad)


def test_submission_carries_provenance_and_no_authority_field() -> None:
    s = to_submission(msg(), CH)
    assert s["source"] == "discord" and s["observed_at_ms"] == message_observed_at_ms(msg())
    p = s["payload"]
    assert p["agent"] == "hermes-macro" and p["channel_id"] == CH.channel_id and p["message_id"] == "1420000000000000001"
    assert p["author"] == {"id": "99", "name": "Hermes Macro", "bot": True}
    assert p["embeds"][0]["title"] == "Macro brief" and p["attachments"][0]["filename"] == "chart.png"
    assert not FORBIDDEN_FIELDS.intersection(p.keys())


def test_submission_passes_quarantine_intake_when_fresh() -> None:
    s = to_submission(msg(), CH)
    verdict = evaluate_submission(s["source"], s["payload"], s["observed_at_ms"] + 60_000, observed_at_ms=s["observed_at_ms"])
    assert verdict.accepted, verdict.reasons


def test_long_content_is_truncated_and_says_so_rather_than_refused() -> None:
    s = to_submission(msg(content="x" * (MAX_CONTENT_CHARS + 500)), CH)
    assert s["payload"]["content_truncated"] and s["payload"]["content"].endswith(TRUNCATED_NOTE)
    assert len(s["payload"]["content"]) <= MAX_CONTENT_CHARS + len(TRUNCATED_NOTE) + 1


def test_timestamp_parsing_handles_z_and_garbage() -> None:
    assert message_observed_at_ms({"timestamp": "2026-09-12T18:30:00Z"}) == 1789237800000
    assert message_observed_at_ms({"timestamp": "not a time"}) is None
    assert message_observed_at_ms({}) is None


def test_newest_id_is_the_largest_snowflake() -> None:
    assert newest_id([{"id": "1420000000000000001"}, {"id": "1420000000000000009"}, {"id": "junk"}]) == "1420000000000000009"
    assert newest_id([]) is None
