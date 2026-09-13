"""The outlook states breadth and measured event reactions, and renders them in text and speech."""

from __future__ import annotations

from tradesync_core.market_outlook import breadth, compose_outlook, key_events
from tradesync_core.outlook_render import outlook_narration, outlook_text


def thesis(direction: str, verdict: str = "NO TRADE", regime: str = "falling"):
    return {
        "verdict": verdict,
        "structure": {"direction": direction, "entry_regime": regime},
        "anchors": {"last_close": 100.0, "low_24h": 95.0, "high_24h": 105.0},
        "invalidation": {"level": 101.0 if direction in ("LONG", "SHORT") else None},
        "confidence": {"evidence_coverage": 0.5},
        "no_trade_conditions": [{"code": "no_demonstrated_edge", "active": True}],
    }


PROFILE = {"kind": "cpi", "label": "US CPI", "occurrences": [],
           "horizons": {"4h": {"n": 6, "median_abs_move_pct": 1.2, "median_range_pct": 1.8, "volatility_ratio": 2.0, "up_share": 0.5}}}
CPI = {"title": "CPI m/m", "country": "USD", "impact": "High", "scheduled_at": "2026-09-15T12:30:00+00:00",
       "minutes_until": 600, "source": "forexfactory", "url": "https://ff", "market_moving": True}


def test_breadth_describes_the_lean_of_the_reads() -> None:
    theses = {f"S{i}-PERP": thesis("SHORT") for i in range(6)}
    theses.update({"L-PERP": thesis("LONG"), "N-PERP": thesis("NONE")})
    b = breadth(theses)
    assert b["lean"] == "bearish" and b["reads"] == {"LONG": 1, "SHORT": 6, "NONE": 1}
    assert breadth({"A": thesis("LONG"), "B": thesis("SHORT")})["lean"] == "mixed"
    assert breadth({"A": thesis("NONE")})["lean"] == "none"
    assert "not a forecast" in b["meaning"]


def test_key_events_keep_upcoming_market_moving_ones_with_reaction_guidance_and_articles() -> None:
    events = [
        CPI,
        {"title": "German ZEW", "country": "EUR", "impact": "Medium", "minutes_until": 100, "market_moving": False},
        {**CPI, "source": "fred"},
        {"title": "FOMC Statement", "impact": "High", "minutes_until": 99999, "scheduled_at": "2026-10-28T18:00:00+00:00"},
    ]
    ke = key_events(events, {"cpi": {"BTC-PERP": PROFILE}}, {"cpi": [{"title": "a", "url": "u", "domain": "d"}]})
    assert len(ke) == 1
    assert ke[0]["kind"] == "cpi" and ke[0]["articles"][0]["url"] == "u" and ke[0]["url"] == "https://ff"
    assert "2.0×" in ke[0]["guidance"][0] and "BTC" in ke[0]["guidance"][0]


def test_outlook_notes_lead_reads_events_and_standing_conditions_and_render() -> None:
    theses = {"BTC-PERP": thesis("SHORT"), "ETH-PERP": thesis("NONE")}
    o = compose_outlook(theses, [CPI], {"cpi": {"BTC-PERP": PROFILE}}, {})
    notes = " ".join(o["notes"])
    assert "BTC reads short" in notes and "wrong beyond 101.00" in notes
    assert "ETH has no admitted read" in notes and "CPI m/m in 10h 0m." in notes
    assert "Standing no-trade conditions: no demonstrated edge (2)." in notes
    text = "\n".join(outlook_text(o))
    assert text.startswith("## Market outlook") and "**CPI m/m**" in text
    spoken = outlook_narration(o)
    assert spoken[0] == o["breadth"]["summary"] and "CPI m/m, in 10h 0m." in spoken
    assert outlook_text({}) == [] and outlook_narration(None) == []
