"""Aggregated books are filed per aggregation, keep only valid levels and say when they are stale."""

from app.depth_books import STALE_AFTER_MS, DepthBooks, parse_side


def message(coin="BTC", bids=None, asks=None, time_ms=1_000):
    return {"channel": "l2Book", "data": {"coin": coin, "time": time_ms, "levels": [
        bids if bids is not None else [{"px": "77000.0", "sz": "12.5", "n": 40}],
        asks if asks is not None else [{"px": "78000.0", "sz": "3.0", "n": 9}],
    ]}}


def test_levels_drop_malformed_and_non_positive_rows() -> None:
    rows = [{"px": "100", "sz": "2"}, {"px": "nan", "sz": "1"}, {"px": "0", "sz": "1"}, {"sz": "1"}, "junk"]
    assert parse_side(rows) == [(100.0, 2.0)]


def test_books_are_kept_per_aggregation_and_report_age() -> None:
    books = DepthBooks()
    assert books.ingest(2, message(), now_ms=10_000)
    assert books.ingest(3, message(bids=[{"px": "77900", "sz": "4"}]), now_ms=10_000)
    latest = books.latest("BTC", now_ms=12_000)
    assert set(latest) == {"2", "3"}
    assert latest["2"]["bids"] == [[77000.0, 12.5]] and latest["3"]["bids"] == [[77900.0, 4.0]]
    assert latest["2"]["age_ms"] == 2_000 and not latest["2"]["stale"]
    assert books.latest("BTC", now_ms=10_000 + STALE_AFTER_MS + 1)["2"]["stale"]


def test_other_channels_and_empty_books_are_ignored() -> None:
    books = DepthBooks()
    assert not books.ingest(2, {"channel": "trades", "data": []})
    assert not books.ingest(2, message(bids=[], asks=[]))
    assert not books.ingest(2, {"channel": "l2Book", "data": {"coin": "BTC", "levels": [[]]}})
    assert books.latest("BTC") == {}
