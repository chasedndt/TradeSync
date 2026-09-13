"""Compose one edition from the per-symbol theses: a headline, the text, the spoken script.

An edition is the thesis for every tracked symbol at one moment. This module
turns those objects into three renderings that all say the same thing:

- ``headline``: one line for a panel or a notification.
- ``text``: the written edition, symbol by symbol, in the SOP's order.
- ``narration``: the same content as a script to be read aloud. Numbers are
  spoken, symbols are said as names, and every no-trade condition is stated
  in words, so a listener hears exactly what a reader sees.

No prose is invented. Every sentence comes from the thesis lines that the
assembler produced from measured evidence.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "thesis_edition_v1"
EDITIONS = ("ny-premarket", "ny-midday", "session-handoff", "manual")

_SPOKEN = {
    "BTC-PERP": "Bitcoin", "ETH-PERP": "Ether", "SOL-PERP": "Solana", "XRP-PERP": "X R P",
    "HYPE-PERP": "Hype", "ZEC-PERP": "Zcash", "NEAR-PERP": "Near", "PUMP-PERP": "Pump",
    "LINK-PERP": "Chainlink", "UNI-PERP": "Uniswap",
}


def spoken_symbol(symbol: str) -> str:
    return _SPOKEN.get(symbol, symbol.replace("-PERP", ""))


def _verdict_counts(theses: Mapping[str, Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for t in theses.values():
        counts[str(t.get("verdict") or "unknown")] = counts.get(str(t.get("verdict") or "unknown"), 0) + 1
    return counts


def headline(edition: str, generated_at: datetime, theses: Mapping[str, Mapping[str, Any]]) -> str:
    counts = _verdict_counts(theses)
    reads = [f"{s.replace('-PERP', '')} {t['structure']['direction']}" for s, t in theses.items()
             if (t.get("structure") or {}).get("direction") in ("LONG", "SHORT")]
    when = generated_at.astimezone(timezone.utc).strftime("%a %d %b %H:%M UTC")
    parts = [f"{edition} edition · {when}", f"{len(theses)} symbols"]
    parts.append(", ".join(f"{n} {v}" for v, n in sorted(counts.items())))
    parts.append("reads: " + (", ".join(reads) if reads else "none admitted"))
    return " · ".join(parts)


def edition_text(edition: str, generated_at: datetime, theses: Mapping[str, Mapping[str, Any]], order: Sequence[str]) -> str:
    when = generated_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    blocks = [f"# Market Command thesis · {edition} · {when}", "", "Private. Assembled from measured evidence only; every line names its source. Not for publication.", ""]
    for symbol in order:
        t = theses.get(symbol)
        if not t:
            continue
        blocks.append(f"## {symbol} · {t.get('verdict', 'unknown')}")
        blocks.append(str(t.get("text") or ""))
        blocks.append("")
    return "\n".join(blocks).rstrip() + "\n"


def _spoken_number(value: Any) -> str:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(v) >= 1000:
        return f"{v:,.0f}".replace(",", " ")
    return f"{v:.2f}"


def narration(edition: str, generated_at: datetime, theses: Mapping[str, Mapping[str, Any]], order: Sequence[str]) -> str:
    """The spoken script. Short sentences; numbers said plainly; conditions in words."""
    when = generated_at.astimezone(timezone.utc).strftime("%H:%M")
    counts = _verdict_counts(theses)
    lines = [
        f"Market Command, {edition.replace('-', ' ')} edition, {when} U T C.",
        f"{len(theses)} symbols reviewed. " + ", ".join(f"{n} {v.lower()}" for v, n in sorted(counts.items())) + ".",
    ]
    for symbol in order:
        t = theses.get(symbol)
        if not t:
            continue
        s, a = t.get("structure") or {}, t.get("anchors") or {}
        name = spoken_symbol(symbol)
        direction = s.get("direction")
        lines.append(f"{name}.")
        lines.append(f"Entry regime {s.get('entry_regime', 'unknown')}.")
        if direction in ("LONG", "SHORT"):
            cov = t.get("confidence", {}).get("evidence_coverage")
            lines.append(f"Paper read {direction.lower()}, evidence coverage {_spoken_number(cov) if cov is not None else 'unknown'}.")
        else:
            lines.append("No admitted paper read.")
        if a.get("last_close") is not None:
            lines.append(f"Last close {_spoken_number(a['last_close'])}. Twenty four hour range {_spoken_number(a.get('low_24h'))} to {_spoken_number(a.get('high_24h'))}.")
        inv = t.get("invalidation") or {}
        if inv.get("level") is not None:
            lines.append(f"Invalidation at {_spoken_number(inv['level'])}.")
        active = [c["code"].replace("_", " ") for c in t.get("no_trade_conditions", []) if c.get("active")]
        lines.append(("No trade. Active conditions: " + ", ".join(active) + ".") if active else "Paper read only. No condition active.")
    lines.append("End of edition. Private thesis, not for publication.")
    return "\n".join(lines)


def compose(edition: str, generated_at: datetime, theses: Mapping[str, Mapping[str, Any]], order: Sequence[str]) -> dict[str, Any]:
    if edition not in EDITIONS:
        raise ValueError(f"unknown edition '{edition}'")
    ordered = [s for s in order if s in theses] + [s for s in theses if s not in order]
    return {
        "schema_version": SCHEMA_VERSION,
        "edition": edition,
        "generated_at": generated_at.astimezone(timezone.utc).isoformat(),
        "symbols": ordered,
        "headline": headline(edition, generated_at, theses),
        "text": edition_text(edition, generated_at, theses, ordered),
        "narration": narration(edition, generated_at, theses, ordered),
        "verdicts": {s: theses[s].get("verdict") for s in ordered},
    }
