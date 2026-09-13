"""An edition renders the same theses three ways without inventing a sentence."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from tradesync_core.thesis_edition import compose, narration, spoken_symbol

T = datetime(2026, 9, 13, 11, 0, tzinfo=timezone.utc)


def thesis(symbol, verdict="NO TRADE", direction="SHORT", active=("no_demonstrated_edge",)):
    return {
        "verdict": verdict,
        "structure": {"entry_regime": "falling", "direction": direction},
        "anchors": {"last_close": 77155.0, "low_24h": 76905.0, "high_24h": 77460.0},
        "invalidation": {"level": 77328.0},
        "confidence": {"evidence_coverage": 0.52},
        "no_trade_conditions": [{"code": c, "active": True} for c in active],
        "text": f"{symbol}: line one.\nVerdict: {verdict}.",
    }


def test_compose_orders_symbols_and_renders_headline_text_and_narration() -> None:
    theses = {"ETH-PERP": thesis("ETH-PERP", direction="NONE"), "BTC-PERP": thesis("BTC-PERP")}
    e = compose("ny-premarket", T, theses, ["BTC-PERP", "ETH-PERP", "SOL-PERP"])
    assert e["symbols"] == ["BTC-PERP", "ETH-PERP"]
    assert e["headline"].startswith("ny-premarket edition · Sun 13 Sep 11:00 UTC · 2 symbols · 2 NO TRADE · reads: BTC SHORT")
    assert "## BTC-PERP · NO TRADE" in e["text"] and e["text"].index("## BTC-PERP") < e["text"].index("## ETH-PERP")
    assert "Not for publication." in e["text"]
    assert e["verdicts"] == {"BTC-PERP": "NO TRADE", "ETH-PERP": "NO TRADE"}


def test_narration_speaks_names_numbers_and_conditions() -> None:
    n = narration("session-handoff", T, {"BTC-PERP": thesis("BTC-PERP")}, ["BTC-PERP"])
    assert "Market Command, session handoff edition, 11:00 U T C." in n
    assert "Bitcoin." in n and "Paper read short, evidence coverage 0.52." in n
    assert "Last close 77 155." in n and "Invalidation at 77 328." in n
    assert "No trade. Active conditions: no demonstrated edge." in n
    assert n.endswith("End of edition. Private thesis, not for publication.")


def test_spoken_symbols_fall_back_to_the_ticker() -> None:
    assert spoken_symbol("SOL-PERP") == "Solana" and spoken_symbol("ABC-PERP") == "ABC"


def test_unknown_edition_is_refused() -> None:
    with pytest.raises(ValueError):
        compose("weekly", T, {}, [])
