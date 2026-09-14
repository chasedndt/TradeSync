"""A plain-prose reading of the timeframe page, drafted by Hermes from the measured numbers only.

It runs as a background job: Hermes takes tens of seconds and the cockpit
proxy cuts requests at 90 s, so the page polls the job. The request goes
through the harness boundary route, so the answer is filed in quarantine with
a receipt and stays advisory. The prompt names the features exactly as the
page does, so the page can link each name to its chart.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any, Mapping

import httpx

from app import agent_connector
from tradesync_core.horizon_features.base import fmt_price
from tradesync_core.horizon_outlook import BANDS, HORIZONS

SELF_URL = os.getenv("STATE_API_SELF_URL", "http://localhost:8000").rstrip("/")
READING_TIMEOUT_S = 300.0
FEATURE_NAMES = ("Trend", "Momentum", "Volatility", "Range position", "Drawdown", "RSI", "Participation")
PROMPT = (
    "Write a private reading of the timeframe outlook for a crypto trader, from the measured facts below only. "
    "Plain prose in four short paragraphs: the lower time frame (3 days and 1 week), the medium time frame "
    "(2 weeks and 1 month), the higher time frame (3 and 6 months), and where the time frames agree or conflict "
    "and which levels matter. Refer to features by exactly these names: " + ", ".join(FEATURE_NAMES) + ". "
    "Each record says what followed past days in the same state; say when a record is too thin to judge. "
    "These are records, not forecasts: do not predict prices, recommend trades or state probabilities beyond "
    "those given. No JSON, no lists, no headings, at most 350 words."
)

_jobs: dict[str, dict[str, Any]] = {}


def job_state(symbol: str) -> dict[str, Any]:
    return dict(_jobs.get(symbol) or {"status": "none"})


def _record(stats: Mapping[str, Any] | None) -> str:
    if not stats or not stats.get("days"):
        return "no comparable days"
    return (f"{stats['days']} comparable days, {stats['independent_windows']} non-overlapping windows (not proof of independence), "
            f"higher {round(float(stats['share_up']) * 100)}% of the time, median {float(stats['median_pct']):+.1f}%, "
            f"middle half {float(stats['p25_pct']):+.1f}% to {float(stats['p75_pct']):+.1f}%")


def facts(symbol: str, outlook: Mapping[str, Any], evaluation: Mapping[str, Any]) -> str:
    history = outlook.get("history") or {}
    lines = [f"Market {symbol}; last daily close {fmt_price(float(outlook['last_close']))}; "
             f"Hyperliquid daily candles {history.get('from')} to {history.get('to')}."]
    reads = {r["key"]: r for r in outlook.get("horizons") or []}
    for band, label in BANDS.items():
        lines.append(f"{label}:")
        for h in (h for h in HORIZONS if h.band == band):
            read = reads.get(h.key) or {}
            if not read.get("available"):
                lines.append(f"- {h.label}: not enough history ({read.get('reason')}).")
                continue
            trend, momentum, implied = read["trend"], read["momentum"], read.get("implied_range") or {}
            basis = read.get("lean_basis") or "same_state"
            line = (f"- {h.label}: close {trend['state'].replace('_', ' ')} its {trend['ma_days']}-day average "
                    f"{fmt_price(float(trend['ma']))}; momentum {float(momentum['change_pct']):+.1f}% over the last {h.label}; "
                    f"record ({basis.replace('_', ' ')}): {_record(read['record'][basis])}; lean {read['lean'].replace('_', ' ')}")
            if implied:
                line += f"; one ordinary move spans {fmt_price(float(implied['low']))} to {fmt_price(float(implied['high']))}"
            lines.append(line + f"; the trend state flips at {fmt_price(float(read['levels']['trend_flips_at']))}.")
            for feature in (evaluation.get(h.key) or {}).get("features") or []:
                lines.append(f"  - {feature['label']}: {feature['text']} Record: {_record(feature['record'])}; "
                             f"lean {str(feature['record_lean']).replace('_', ' ')}.")
    return "\n".join(lines)


async def run_reading(symbol: str, outlook: Mapping[str, Any], evaluation: Mapping[str, Any]) -> None:
    started_at = datetime.now(timezone.utc).isoformat()
    _jobs[symbol] = {"status": "running", "started_at": started_at}
    if not agent_connector.configured():
        _jobs[symbol] = {"status": "not_configured", "started_at": started_at}
        return
    prompt = PROMPT + "\n\nFACTS:\n" + facts(symbol, outlook, evaluation)[:24000]
    begun = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=READING_TIMEOUT_S, trust_env=False) as client:
            response = await client.post(f"{SELF_URL}/state/agents/harness/ask", json={"intent": "summarise", "prompt": prompt})
    except httpx.HTTPError as exc:
        _jobs[symbol] = {"status": "unavailable", "detail": type(exc).__name__, "started_at": started_at}
        return
    done = {"started_at": started_at, "finished_at": datetime.now(timezone.utc).isoformat(),
            "elapsed_ms": int((time.monotonic() - begun) * 1000)}
    if response.status_code == 422:
        _jobs[symbol] = {"status": "refused", "detail": str(response.json().get("detail", ""))[:300], **done}
    elif response.status_code != 200:
        _jobs[symbol] = {"status": "unavailable", "detail": f"HTTP {response.status_code}", **done}
    else:
        body = response.json()
        _jobs[symbol] = {"status": "ok", "content": body.get("content", ""), "model": body.get("model"),
                         "receipt": body.get("receipt"), "authority": "advisory_only",
                         "source": "Hermes gateway via the harness boundary", **done}
