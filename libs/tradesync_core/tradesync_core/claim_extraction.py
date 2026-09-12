"""Turn quarantined material into measurable claims, or say why it is not one.

A claim is the smallest thing a track record can be built on: *this source
said this direction on this symbol at this time*. Extraction here is
rule-based and deliberately conservative. It looks for a symbol the system
tracks and an unambiguous direction word near it. Anything else — a report
with no direction, a post that says both, a ticker outside the universe — is
recorded as "no claim" with the reason, never guessed at.

Conservative on purpose: a claim that was invented by the extractor would be
scored against outcomes and could earn a source a weight it never asked for.
A missed claim only costs coverage, and coverage is counted.

No model is involved. A harness could later propose claims through the same
``Claim`` shape, marked with its own ``extractor`` name, and be measured on
exactly the same footing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

EXTRACTOR = "rule_v1"
DEFAULT_HORIZON_MINUTES = 240
ALLOWED_HORIZONS = (15, 60, 240)

# Ticker aliases -> the Hyperliquid perp the system tracks. Only listed
# symbols can carry a claim; a source talking about anything else is coverage
# the system does not have, not a claim it should measure against a proxy.
SYMBOL_ALIASES: dict[str, str] = {
    "BTC": "BTC-PERP", "BTCUSD": "BTC-PERP", "BTCUSDT": "BTC-PERP", "BTCUSDC": "BTC-PERP", "BITCOIN": "BTC-PERP", "XBT": "BTC-PERP",
    "ETH": "ETH-PERP", "ETHUSD": "ETH-PERP", "ETHUSDT": "ETH-PERP", "ETHUSDC": "ETH-PERP", "ETHEREUM": "ETH-PERP",
    "SOL": "SOL-PERP", "SOLUSD": "SOL-PERP", "SOLUSDT": "SOL-PERP", "SOLANA": "SOL-PERP",
    "XRP": "XRP-PERP", "XRPUSD": "XRP-PERP", "XRPUSDT": "XRP-PERP",
    "HYPE": "HYPE-PERP", "HYPEUSD": "HYPE-PERP", "HYPEUSDT": "HYPE-PERP",
    "ZEC": "ZEC-PERP", "ZECUSD": "ZEC-PERP", "ZECUSDT": "ZEC-PERP",
    "NEAR": "NEAR-PERP", "NEARUSD": "NEAR-PERP", "NEARUSDT": "NEAR-PERP",
    "LINK": "LINK-PERP", "LINKUSD": "LINK-PERP", "LINKUSDT": "LINK-PERP",
    "UNI": "UNI-PERP", "UNIUSD": "UNI-PERP", "UNIUSDT": "UNI-PERP",
    "PUMP": "PUMP-PERP", "PUMPUSD": "PUMP-PERP", "PUMPUSDT": "PUMP-PERP",
}

_LONG_WORDS = r"(?:bullish|long|buy|buys|bought|breakout up|cross(?:ed|es)? (?:up|above)|reclaim(?:ed|s)?|higher high|bid)"
_SHORT_WORDS = r"(?:bearish|short|sell|sells|sold|breakdown|cross(?:ed|es)? (?:down|below)|lost|lower low|offer)"
_LONG = re.compile(rf"\b{_LONG_WORDS}\b", re.IGNORECASE)
_SHORT = re.compile(rf"\b{_SHORT_WORDS}\b", re.IGNORECASE)
_NEGATED = re.compile(r"\b(?:no|not|never|without|invalid|invalidated|no-trade|no trade|hold)\b", re.IGNORECASE)
# A clause that reports on the past is bookkeeping, not a call: the fleet's
# paper-outcome resolver saying "SOL short resolved +0.4%" is describing a
# trade it already scored. Such clauses abstain.
_REPORTING = re.compile(
    r"\b(?:resolved|resolver|resolves|outcome|outcomes|ledger|scan|scanned|records?|recap|scorecard|scorecards|"
    r"summary|report|reported|closed|expired|measured|hit rate|win rate|pnl|p&l|target hit|stop hit|stopped|"
    r"filled|fill|forward-signal|paper outcomes?)\b",
    re.IGNORECASE,
)
_TOKEN = re.compile(r"\$?\b([A-Z]{2,8})(?:/USDT?|USDT?|-PERP)?\b")
_INTERVAL = re.compile(r"^\s*(\d+)\s*([mhdMHD]?)\s*$")
_WINDOW = 160  # characters of a clause that are read for a direction
_CLAUSE = re.compile(r"(?:[.!?;\n]|\s[•\-–]\s)+")


@dataclass(frozen=True)
class Claim:
    source: str
    source_id: str
    symbol: str
    direction: str
    horizon_minutes: int
    claimed_at_ms: int
    extractor: str
    excerpt: str


@dataclass(frozen=True)
class NoClaim:
    reason: str


def normalise_symbol(raw: str) -> str | None:
    key = raw.upper().strip().lstrip("$")
    for suffix in ("-PERP", "/USDT", "/USD", "PERP"):
        if key.endswith(suffix):
            key = key[: -len(suffix)]
    return SYMBOL_ALIASES.get(key)


def horizon_for_interval(interval: str | None) -> int:
    """A chart interval to the outcome horizon it is judged on.

    Sub-hour charts are judged at 15 or 60 minutes; hourly and above at 240.
    Coarser is never chosen than the system measures.
    """
    if not interval:
        return DEFAULT_HORIZON_MINUTES
    m = _INTERVAL.match(str(interval))
    if not m:
        return DEFAULT_HORIZON_MINUTES
    n, unit = int(m.group(1)), m.group(2).lower()
    minutes = n * {"": 1, "m": 1, "h": 60, "d": 1440}[unit]
    if minutes <= 5:
        return 15
    if minutes <= 30:
        return 60
    return 240


def direction_of(text: str) -> str | None:
    """One unambiguous direction, or None. Negated, reporting or mixed text abstains."""
    if _NEGATED.search(text) or _REPORTING.search(text):
        return None
    longs, shorts = bool(_LONG.search(text)), bool(_SHORT.search(text))
    if longs == shorts:
        return None
    return "LONG" if longs else "SHORT"


def _ms(iso: str | None, fallback_ms: int) -> int:
    if not isinstance(iso, str):
        return fallback_ms
    try:
        parsed = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return fallback_ms
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def _excerpt(text: str, limit: int = 240) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _from_text(
    source: str, source_id: str, text: str, claimed_at_ms: int, horizon: int
) -> list[Claim] | NoClaim:
    """Claims from free text: each tracked symbol with one clear direction nearby."""
    if not text.strip():
        return NoClaim("empty text")
    # A post whose heading is a ledger or outcome report describes trades
    # already taken. Its body will mention symbols and sides throughout;
    # none of them is a fresh call.
    if _REPORTING.search(text[:_WINDOW]):
        return NoClaim("post is a report or ledger, not a call")
    found: dict[str, set[str]] = {}
    # Judge each clause on its own: "BTC bearish. ETH bullish." is two claims,
    # not one symbol with both directions.
    for clause in _CLAUSE.split(text):
        symbols = {s for s in (normalise_symbol(m.group(1)) for m in _TOKEN.finditer(clause)) if s}
        if not symbols:
            continue
        direction = direction_of(clause[:_WINDOW * 2])
        if direction:
            for symbol in symbols:
                found.setdefault(symbol, set()).add(direction)
    if not found:
        return NoClaim("no tracked symbol with a clear direction nearby")
    claims = [
        Claim(source, source_id, symbol, next(iter(dirs)), horizon, claimed_at_ms, EXTRACTOR, _excerpt(text))
        for symbol, dirs in sorted(found.items())
        if len(dirs) == 1
    ]
    return claims or NoClaim("every symbol mentioned had both directions nearby")


def _from_tradingview(payload: Mapping[str, Any], received_ms: int) -> list[Claim] | NoClaim:
    symbol = normalise_symbol(str(payload.get("ticker") or ""))
    if symbol is None:
        return NoClaim(f"ticker '{payload.get('ticker')}' is outside the tracked universe")
    alert = payload.get("alert") or {}
    indicator = str(payload.get("indicator") or "").strip()
    source_id = indicator.split(" - ")[0].strip() or "tradingview"
    text = " ".join(str(v) for v in (payload.get("action"), indicator, alert.get("note"), alert.get("message"), alert.get("direction")) if v)
    direction = direction_of(text)
    if direction is None:
        return NoClaim("alert names no unambiguous direction (action/indicator/note)")
    horizon = horizon_for_interval(str(payload.get("interval") or alert.get("interval") or ""))
    claimed_at = _ms(alert.get("time"), received_ms)
    return [Claim("tradingview", source_id, symbol, direction, horizon, claimed_at, EXTRACTOR, _excerpt(text))]


def _from_discord(payload: Mapping[str, Any], received_ms: int) -> list[Claim] | NoClaim:
    parts = [str(payload.get("content") or "")]
    for e in payload.get("embeds") or []:
        parts.extend(str(e.get(k) or "") for k in ("title", "description"))
        parts.extend(f"{f.get('name')}: {f.get('value')}" for f in e.get("fields") or [])
    text = "\n".join(p for p in parts if p)
    return _from_text("discord", str(payload.get("agent") or "discord"), text, _ms(payload.get("posted_at"), received_ms), DEFAULT_HORIZON_MINUTES)


def _from_hermes(payload: Mapping[str, Any], received_ms: int, observed_ms: int | None) -> list[Claim] | NoClaim:
    return _from_text("chaseos", str(payload.get("agent") or "hermes"), str(payload.get("content") or ""), observed_ms or received_ms, DEFAULT_HORIZON_MINUTES)


def extract(
    source: str, payload: Mapping[str, Any], received_ms: int, observed_ms: int | None = None
) -> list[Claim] | NoClaim:
    """Claims from one quarantine row, by payload schema."""
    schema = str(payload.get("schema_version") or "")
    if source == "tradingview" and schema == "tradingview_alert_v1":
        return _from_tradingview(payload, received_ms)
    if source == "discord" and schema == "discord_message_v1":
        return _from_discord(payload, received_ms)
    if source == "chaseos" and schema == "hermes_job_output_v1":
        return _from_hermes(payload, received_ms, observed_ms)
    return NoClaim(f"no extractor for source '{source}' schema '{schema or 'none'}'")


def claims_only(result: list[Claim] | NoClaim) -> Sequence[Claim]:
    return result if isinstance(result, list) else ()
