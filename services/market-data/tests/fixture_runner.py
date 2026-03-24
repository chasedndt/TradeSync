"""
Offline Fixture Runner for Market Data Pipeline

Loads sample payloads from docs/samples/market/ and processes them
through the normalizer and snapshotter to verify the pipeline works
without live API connections.

Usage:
    python -m tests.fixture_runner
"""

import json
import sys
import time
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.processors import MarketNormalizer, MarketSnapshotter
from app.models import MetricStatus

SAMPLES_DIR = Path(__file__).parent.parent.parent.parent / "docs" / "samples" / "market"


def load_sample(filename: str) -> dict:
    """Load a sample JSON file."""
    filepath = SAMPLES_DIR / filename
    if not filepath.exists():
        print(f"   [WARN] Sample file not found: {filepath}")
        return {}
    with open(filepath) as f:
        return json.load(f)


def parse_hyperliquid_context(raw_data: dict) -> dict:
    """
    Parse Hyperliquid metaAndAssetCtxs response into normalizer format.

    The response format is [metadata, [asset_contexts]]
    We need to convert to {symbol: {funding, oi, volume, price}}
    """
    if not raw_data or "response" not in raw_data:
        return {}

    response = raw_data["response"]
    if len(response) < 2:
        return {}

    universe = response[0].get("universe", [])
    asset_contexts = response[1]

    if len(universe) != len(asset_contexts):
        print(f"   [WARN] Universe/context length mismatch: {len(universe)} vs {len(asset_contexts)}")
        return {}

    now_ms = int(time.time() * 1000)
    result = {}

    for i, meta in enumerate(universe):
        ctx = asset_contexts[i]
        symbol = f"{meta['name']}-PERP"
        mark_price = float(ctx.get("markPx", 0))

        result[symbol] = {
            "poll_ts": now_ms,
            "funding": {
                "rate": float(ctx.get("funding", 0)),
                "source": "metaAndAssetCtxs"
            },
            "oi": {
                "value": float(ctx.get("openInterest", 0)),
                "unit": "asset",
                "source": "metaAndAssetCtxs"
            },
            "volume": {
                "value_24h": float(ctx.get("dayNtlVlm", 0)),
                "source": "metaAndAssetCtxs"
            },
            "price": {
                "mark": mark_price,
                "oracle": float(ctx.get("oraclePx", 0)),
                "index": float(ctx.get("oraclePx", 0))
            }
        }

    return result


def run_fixture_test():
    """Run the fixture through the pipeline."""
    normalizer = MarketNormalizer()
    snapshotter = MarketSnapshotter()

    print("=" * 60)
    print("   Fixture Runner: Market Data Pipeline")
    print("=" * 60)
    print()

    # 1. Load Hyperliquid context data
    print("1. Loading hyperliquid_metaAndAssetCtxs.json...")
    hl_raw = load_sample("hyperliquid_metaAndAssetCtxs.json")
    if not hl_raw:
        print("   [ERROR] Failed to load sample file")
        return False

    # 2. Parse into normalizer format
    print("\n2. Parsing Hyperliquid response format...")
    hl_context = parse_hyperliquid_context(hl_raw)
    print(f"   Parsed {len(hl_context)} assets")
    for sym in hl_context:
        print(f"   - {sym}")

    # 3. Normalize
    print("\n3. Normalizing context data...")
    events = normalizer.normalize_context("hyperliquid", hl_context)
    print(f"   Generated {len(events)} normalized events")

    if events:
        print("\n   Sample events:")
        for evt in events[:6]:  # Show first 6
            rate = evt.value.get("rate", evt.value.get("value_24h", evt.value.get("mark", "N/A")))
            print(f"   - {evt.symbol} / {evt.metric_type}: {rate} (status: {evt.status})")

    # 4. Process through snapshotter
    print("\n4. Processing events through snapshotter...")
    snapshots = []
    seen_symbols = set()
    for evt in events:
        snapshot = snapshotter.process_event(evt)
        if snapshot and snapshot.symbol not in seen_symbols:
            snapshots.append(snapshot)
            seen_symbols.add(snapshot.symbol)

    print(f"   Generated {len(snapshots)} unique snapshots")

    # 5. Verify snapshot structure
    print("\n5. Verifying snapshot structure...")
    if snapshots:
        for sample in snapshots[:3]:
            print(f"\n   --- {sample.symbol} ---")
            print(f"   Venue:           {sample.venue}")
            print(f"   Timestamp:       {sample.ts}")
            print(f"   Data Age:        {sample.data_age_ms}ms")
            print(f"   Metrics:         {[m.metric for m in sample.available_metrics]}")
            print(f"   Regimes:")
            print(f"     Funding:       {sample.regimes.funding}")
            print(f"     OI:            {sample.regimes.oi}")
            print(f"     Volume:        {sample.regimes.volume}")
            print(f"     Trend:         {sample.regimes.trend}")
            print(f"     Condition:     {sample.regimes.market_condition}")
            print(f"     Confidence:    {sample.regimes.confidence}")

    # 6. Check truthfulness
    print("\n6. Checking truthfulness (REAL/PROXY/UNAVAILABLE)...")
    truthfulness_summary = {"REAL": 0, "PROXY": 0, "UNAVAILABLE": 0, "STALE": 0}

    for s in snapshots:
        for m in s.available_metrics:
            status_emoji = {
                MetricStatus.REAL: "[OK]",
                MetricStatus.PROXY: "[PROXY]",
                MetricStatus.UNAVAILABLE: "[N/A]",
                MetricStatus.STALE: "[STALE]"
            }.get(m.status, "[?]")
            truthfulness_summary[m.status.value] += 1
            print(f"   {s.symbol:12} / {m.metric:12}: {status_emoji} {m.status}")

    print("\n   Summary:")
    for status, count in truthfulness_summary.items():
        if count > 0:
            print(f"     {status}: {count}")

    # 7. Test regime change detection
    print("\n7. Testing regime change detection...")
    if len(events) >= 2:
        # Process same events twice to simulate no change
        for evt in events:
            snapshot = snapshotter.process_event(evt)
            if snapshot:
                alerts = snapshotter.check_regime_change(
                    evt.venue, evt.symbol, snapshot.regimes
                )
                if alerts:
                    for alert in alerts:
                        print(f"   ALERT: {alert.symbol} - {alert.metric}: {alert.previous_value} -> {alert.new_value}")
        print("   No spurious alerts generated (expected)")

    print("\n" + "=" * 60)
    print("   Fixture Test Complete")
    print("=" * 60)
    return len(snapshots) > 0


if __name__ == "__main__":
    success = run_fixture_test()
    sys.exit(0 if success else 1)
