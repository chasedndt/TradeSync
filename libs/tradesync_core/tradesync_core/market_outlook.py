"""The outlook a trader reads first: where the market is leaning and what is coming.

Composed from things already measured: the per-symbol theses (paper reads,
regimes, verdicts), the week's scheduled events, the measured reaction of
each event kind on past releases (``event_reactions``), and recent articles
on those events. It states breadth, not a forecast: "seven of ten reads are
short" is a fact about the evidence, and it is labelled as such.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from .event_reactions import guidance, kind_for_title

LOOKAHEAD_MINUTES = 7 * 24 * 60
LEAD_SYMBOLS = ("BTC-PERP", "ETH-PERP")


def breadth(theses: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    reads = {"LONG": 0, "SHORT": 0, "NONE": 0}
    regimes: dict[str, int] = {}
    verdicts: dict[str, int] = {}
    for t in theses.values():
        s = t.get("structure") or {}
        reads[s.get("direction") if s.get("direction") in ("LONG", "SHORT") else "NONE"] += 1
        regimes[str(s.get("entry_regime") or "unknown")] = regimes.get(str(s.get("entry_regime") or "unknown"), 0) + 1
        verdicts[str(t.get("verdict") or "unknown")] = verdicts.get(str(t.get("verdict") or "unknown"), 0) + 1
    total = max(1, sum(reads.values()))
    directional = reads["LONG"] + reads["SHORT"]
    if directional == 0:
        lean, text = "none", "No admitted paper read on any tracked market."
    elif reads["SHORT"] >= 2 * max(1, reads["LONG"]) and reads["SHORT"] / total >= 0.5:
        lean, text = "bearish", f"Bearish lean: {reads['SHORT']} of {total} markets read short, {reads['LONG']} long."
    elif reads["LONG"] >= 2 * max(1, reads["SHORT"]) and reads["LONG"] / total >= 0.5:
        lean, text = "bullish", f"Bullish lean: {reads['LONG']} of {total} markets read long, {reads['SHORT']} short."
    else:
        lean, text = "mixed", f"Mixed: {reads['LONG']} long, {reads['SHORT']} short, {reads['NONE']} without a read."
    return {"lean": lean, "summary": text, "reads": reads, "regimes": regimes, "verdicts": verdicts,
            "meaning": "breadth of the paper reads across the tracked universe; a description of the evidence, not a forecast"}


def lead_reads(theses: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for symbol in LEAD_SYMBOLS:
        t = theses.get(symbol)
        if not t:
            continue
        s, a, inv = t.get("structure") or {}, t.get("anchors") or {}, t.get("invalidation") or {}
        out.append({
            "symbol": symbol, "direction": s.get("direction"), "regime": s.get("entry_regime"), "verdict": t.get("verdict"),
            "last": a.get("last_close"), "low_24h": a.get("low_24h"), "high_24h": a.get("high_24h"),
            "invalidation": inv.get("level"), "coverage": (t.get("confidence") or {}).get("evidence_coverage"),
        })
    return out


def key_events(events: Sequence[Mapping[str, Any]], profiles: Mapping[str, Mapping[str, Any]],
               articles: Mapping[str, Sequence[Mapping[str, Any]]]) -> list[dict[str, Any]]:
    """Upcoming High-impact or market-moving events, each with its measured reaction and reading."""
    out = []
    seen: set[tuple[str, str]] = set()
    for e in events:
        minutes = e.get("minutes_until")
        if not isinstance(minutes, int) or minutes < -60 or minutes > LOOKAHEAD_MINUTES:
            continue
        if not (e.get("impact") == "High" or e.get("market_moving")):
            continue
        kind = kind_for_title(str(e.get("title") or ""))
        key = (str(e.get("title")), str(e.get("scheduled_at"))[:10])
        if key in seen:
            continue
        seen.add(key)
        reaction = {}
        notes = []
        if kind:
            for symbol in LEAD_SYMBOLS:
                prof = (profiles.get(kind.key) or {}).get(symbol)
                if prof:
                    reaction[symbol] = prof["horizons"]
                    notes.append(guidance(kind.label, symbol.replace("-PERP", ""), prof))
        out.append({
            "title": e.get("title"), "country": e.get("country"), "impact": e.get("impact"),
            "scheduled_at": e.get("scheduled_at"), "minutes_until": minutes, "source": e.get("source"),
            "url": e.get("url") or (kind.source_url if kind else None),
            "forecast": e.get("forecast"), "previous": e.get("previous"),
            "kind": kind.key if kind else None, "kind_label": kind.label if kind else None,
            "reaction": reaction, "guidance": notes,
            "articles": list(articles.get(kind.key, []))[:4] if kind else [],
        })
    return out


def trader_notes(breadth_: Mapping[str, Any], leads: Sequence[Mapping[str, Any]], events: Sequence[Mapping[str, Any]],
                 theses: Mapping[str, Mapping[str, Any]]) -> list[str]:
    notes = [breadth_["summary"]]
    for r in leads:
        if r.get("direction") in ("LONG", "SHORT") and r.get("invalidation") is not None:
            notes.append(f"{r['symbol'].replace('-PERP', '')} reads {r['direction'].lower()} in a {r.get('regime')} regime; "
                         f"that read is wrong beyond {r['invalidation']:,.2f}.")
        elif r.get("last") is not None:
            notes.append(f"{r['symbol'].replace('-PERP', '')} has no admitted read; 24h range {r.get('low_24h', 0):,.2f} to {r.get('high_24h', 0):,.2f}.")
    soon = [e for e in events if e["minutes_until"] <= 48 * 60]
    for e in soon[:3]:
        when = "under way" if e["minutes_until"] < 0 else f"in {e['minutes_until'] // 60}h {e['minutes_until'] % 60}m"
        notes.append(f"{e['title']} {when}." + (f" {e['guidance'][0]}" if e["guidance"] else ""))
    active = {}
    for t in theses.values():
        for c in t.get("no_trade_conditions", []):
            if c.get("active"):
                active[c["code"]] = active.get(c["code"], 0) + 1
    if active:
        notes.append("Standing no-trade conditions: " + ", ".join(f"{k.replace('_', ' ')} ({v})" for k, v in sorted(active.items(), key=lambda kv: -kv[1])) + ".")
    return notes


def compose_outlook(theses: Mapping[str, Mapping[str, Any]], events: Sequence[Mapping[str, Any]],
                    profiles: Mapping[str, Mapping[str, Any]], articles: Mapping[str, Sequence[Mapping[str, Any]]],
                    now: datetime | None = None, profile_window: Mapping[str, Any] | None = None) -> dict[str, Any]:
    b = breadth(theses)
    leads = lead_reads(theses)
    ke = key_events(events, profiles, articles)
    return {
        "schema_version": "market_outlook_v1",
        "generated_at": (now or datetime.now(timezone.utc)).isoformat(),
        "breadth": b,
        "leads": leads,
        "key_events": ke,
        "notes": trader_notes(b, leads, ke, theses),
        "reaction_method": {
            "measure": "move from the last hourly close at or before each past release to the close 1, 4 and 24 hours later, on Hyperliquid candles",
            "baseline": "the same move at the same time of day on days with no scheduled release within 24 hours",
            "window": dict(profile_window or {}),
            "caveat": "a record of past reactions, not a forecast; sample sizes are shown",
        },
    }
