"""Binance liquidations normalise to the shared shape; Bybit and Binance merge newest first; OI history parses."""

from app import binance_liquidations, liquidation_events
from app.open_interest_history import parse

MARKETS = binance_liquidations.symbol_map(["BTC-PERP", "ETH-PERP"])


def force_order(side="SELL", symbol="BTCUSDT", ts=1_000_000, ap="77000", z="0.5"):
    return {"e": "forceOrder", "E": ts, "o": {"s": symbol, "S": side, "q": z, "p": "76900", "ap": ap, "X": "FILLED", "z": z, "T": ts}}


def test_a_sell_liquidation_closes_a_long_and_notional_uses_the_average_fill() -> None:
    [event] = binance_liquidations.normalize(force_order(), received_at=1_000.5, markets=MARKETS)
    assert event["position_side"] == "long" and event["symbol"] == "BTC-PERP"
    assert event["price"] == 77000.0 and event["size"] == 0.5 and event["notional_usd"] == 38500.0
    [short] = binance_liquidations.normalize(force_order(side="BUY"), received_at=1_000.5, markets=MARKETS)
    assert short["position_side"] == "short" and short["id"] != event["id"]


def test_untracked_old_or_malformed_orders_are_dropped() -> None:
    assert binance_liquidations.normalize(force_order(symbol="DOGEUSDT"), 1_000.5, MARKETS) == []
    assert binance_liquidations.normalize(force_order(ts=1_000), 1_000_000.0, MARKETS) == []  # older than an hour
    assert binance_liquidations.normalize({"e": "forceOrder", "o": {"S": "SELL"}}, 1_000.5, MARKETS) == []
    assert binance_liquidations.normalize([force_order(), force_order(side="BUY")], 1_000.5, MARKETS)[1]["position_side"] == "short"


def test_bybit_and_binance_merge_into_one_shape_newest_first() -> None:
    bybit = {"connection": {"state": "connected"}, "events": [{
        "id": "a", "symbol": "BTC-PERP", "event_time": 10.0, "received_at": 10.2, "position_side": "short",
        "bankruptcy_price": 77100.0, "size": 1.0, "bankruptcy_notional_usdt": 77100.0}]}
    binance = {"connection": {"state": "connected"}, "events": binance_liquidations.normalize(force_order(ts=20_000), 20.5, MARKETS)}
    merged = liquidation_events.merged("BTC-PERP", bybit, binance)
    assert [e["source"] for e in merged["events"]] == ["binance", "bybit"]
    assert merged["events"][1]["price_kind"] == "bankruptcy" and merged["events"][0]["price_kind"] == "average_fill"
    assert merged["authority"] == "context_only"


def test_open_interest_history_rows_parse_and_sort() -> None:
    rows = parse([
        {"timestamp": 7200000, "sumOpenInterest": "2", "sumOpenInterestValue": "150000"},
        {"timestamp": 3600000, "sumOpenInterest": "1", "sumOpenInterestValue": "76000"},
        {"timestamp": "x", "sumOpenInterest": "1", "sumOpenInterestValue": "1"},
    ])
    assert rows == [{"time": 3600, "oi_coins": 1.0, "oi_usd": 76000.0}, {"time": 7200, "oi_coins": 2.0, "oi_usd": 150000.0}]
