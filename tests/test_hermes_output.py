"""A Hermes output file becomes labelled, bounded quarantine material."""

from __future__ import annotations

from tradesync_core.hermes_output import (
    MAX_CONTENT_CHARS,
    TRUNCATED_NOTE,
    delivery_of,
    parse_filename,
    to_submission,
)
from tradesync_core.quarantine import FORBIDDEN_FIELDS, evaluate_submission

JOB = {"id": "0dc74012e8d8", "name": "StrikeZone Hyperliquid closed-candle forward test", "enabled": True,
       "deliver": "discord:1529610931687002334", "schedule": {"kind": "cron", "expr": "*/15 * * * *", "display": "*/15 * * * *"}}
CHANNELS = {"1529610931687002334": "sz-hl-forward-test"}


def test_filename_parses_job_id_and_stamp_and_ignores_latest_copies() -> None:
    out = parse_filename("0dc74012e8d8_20260912_193207.txt")
    assert out and out.job_id == "0dc74012e8d8" and out.ran_at_ms == 1789241527000
    assert parse_filename("0dc74012e8d8") is None
    assert parse_filename("0dc74012e8d8_20261399_000000.txt") is None
    assert parse_filename("notes.txt") is None


def test_markdown_runs_in_per_job_directories_parse_too() -> None:
    from tradesync_core.hermes_output import parse_markdown_run

    out = parse_markdown_run("0c42e5b6b468", "2026-08-01_19-53-04.md")
    assert out and out.job_id == "0c42e5b6b468" and out.stamp == "2026-08-01_19-53-04"
    assert out.filename == "0c42e5b6b468/2026-08-01_19-53-04.md"
    assert parse_markdown_run("notajob", "2026-08-01_19-53-04.md") is None
    assert parse_markdown_run("0c42e5b6b468", "latest.md") is None


def test_delivery_names_the_channel_label_or_local() -> None:
    assert delivery_of(JOB, CHANNELS) == {"kind": "discord", "channel_id": "1529610931687002334", "channel_label": "sz-hl-forward-test"}
    assert delivery_of({"deliver": "local"}, CHANNELS)["kind"] == "local"
    assert delivery_of(None, CHANNELS)["kind"] == "local"
    assert delivery_of({"deliver": "discord:999"}, CHANNELS)["channel_label"] == "999"


def test_submission_is_labelled_bounded_and_passes_intake() -> None:
    out = parse_filename("0dc74012e8d8_20260912_193207.txt")
    s = to_submission(out, "BTC forward test: 3 of 4 closed candles agreed.", JOB, CHANNELS, observed_at_ms=1_789_241_600_000)
    p = s["payload"]
    assert s["source"] == "chaseos" and s["observed_at_ms"] == 1_789_241_600_000
    assert p["agent"] == JOB["name"] and p["job_id"] == "0dc74012e8d8" and p["schedule"] == "*/15 * * * *"
    assert p["delivery"]["channel_label"] == "sz-hl-forward-test" and p["ran_at_stamp"] == "20260912_193207"
    assert not FORBIDDEN_FIELDS.intersection(p.keys())
    verdict = evaluate_submission(s["source"], p, s["observed_at_ms"] + 30_000, observed_at_ms=s["observed_at_ms"])
    assert verdict.accepted, verdict.reasons


def test_unknown_job_gets_a_stable_fallback_label_and_the_stamp_as_observed() -> None:
    out = parse_filename("abcdefabcdef_20260912_120000.txt")
    s = to_submission(out, "x", None, {})
    assert s["payload"]["agent"] == "hermes-job-abcdefabcdef" and s["observed_at_ms"] == out.ran_at_ms


def test_the_fleets_own_silent_stub_is_recognised() -> None:
    from tradesync_core.hermes_output import is_silent

    stub = "# Cron Job: x\n\n**Job ID:** 1\n**Mode:** no_agent (script)\n**Status:** silent (empty output)\n"
    assert is_silent(stub)
    assert not is_silent("# Cron Job: x\n\n**Status:** ok\n\nBTC thesis: ...")


def test_long_output_is_truncated_and_says_so() -> None:
    out = parse_filename("abcdefabcdef_20260912_120000.txt")
    s = to_submission(out, "y" * (MAX_CONTENT_CHARS + 10), JOB, CHANNELS)
    assert s["payload"]["content_truncated"] and s["payload"]["content"].endswith(TRUNCATED_NOTE)
