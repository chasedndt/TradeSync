"""Received liquidations from every context venue in one shape: source, side, price, size, notional.

Bybit reports bankruptcy prices; Binance reports average fill prices. Both are
other venues' liquidations, kept as context for Hyperliquid, never authority.
"""

from __future__ import annotations

from typing import Any, Mapping


def from_bybit(event: Mapping[str, Any]) -> dict[str, Any] | None:
    try:
        return {
            "id": str(event["id"]), "source": "bybit", "symbol": str(event["symbol"]),
            "event_time": float(event["event_time"]), "received_at": float(event["received_at"]),
            "position_side": str(event["position_side"]), "price": float(event["bankruptcy_price"]),
            "size": float(event["size"]), "notional_usd": float(event["bankruptcy_notional_usdt"]),
            "price_kind": "bankruptcy",
        }
    except (KeyError, TypeError, ValueError):
        return None


def from_binance(event: Mapping[str, Any]) -> dict[str, Any] | None:
    try:
        return {
            "id": str(event["id"]), "source": "binance", "symbol": str(event["symbol"]),
            "event_time": float(event["event_time"]), "received_at": float(event["received_at"]),
            "position_side": str(event["position_side"]), "price": float(event["price"]),
            "size": float(event["size"]), "notional_usd": float(event["notional_usd"]),
            "price_kind": "average_fill",
        }
    except (KeyError, TypeError, ValueError):
        return None


def merged(symbol: str, bybit: Mapping[str, Any], binance: Mapping[str, Any]) -> dict[str, Any]:
    events = [e for e in (from_bybit(x) for x in bybit.get("events") or []) if e]
    events += [e for e in (from_binance(x) for x in binance.get("events") or []) if e]
    events.sort(key=lambda e: e["event_time"], reverse=True)
    return {
        "symbol": symbol,
        "sources": {"bybit": bybit.get("connection"), "binance": binance.get("connection")},
        "events": events,
        "window_seconds": 3600,
        "authority": "context_only",
        "note": "Liquidations received from Bybit and Binance USDT contracts in the last hour. Hyperliquid publishes no market-wide liquidation feed.",
    }
