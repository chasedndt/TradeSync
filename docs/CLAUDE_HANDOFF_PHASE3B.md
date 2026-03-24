# Claude Code Handoff — Phase 3B Completion

> **Purpose**: This document provides complete context for Claude Code to resume Phase 3B immediately when limits reset.
> **Last Updated**: 2026-01-21T23:38:00Z

---

## Current State Summary

Phase 3B (Market Data Expansion) is **85% complete**. The core backend infrastructure is done. Only UI wiring and verification remain.

### ✅ Completed (Steps 3B.0 – 3B.5)

| Step | Description | Status |
|------|-------------|--------|
| 3B.0 | Provider Discovery | ✅ `docs/providers/MARKET_PROVIDER_MATRIX.md`, `docs/samples/market/` |
| 3B.1 | MarketSnapshot Contract | ✅ `docs/contracts/MARKET_CONTRACT.md`, `SYMBOL_NORMALIZATION.md` |
| 3B.2 | Ingestion Pipeline | ✅ `services/market-data/` (Poller, Normalizer, Snapshotter) |
| 3B.3 | Persistence Strategy | ✅ `docs/architecture/market_storage.md`, RedisStore implemented |
| 3B.4 | State API Endpoints | ✅ `/state/market/snapshot`, `/timeseries`, `/alerts` in state-api |
| 3B.5 | Regime Engine | ✅ Funding/OI/Vol/Trend regimes computed in Snapshotter |
| 3B.6 | UI Wiring (partial) | ✅ `/market` page fully wired with truthful badges |

### ⏳ Remaining (Steps 3B.6 partial + 3B.7)

| Task | File(s) to Modify | Description |
|------|-------------------|-------------|
| Overview Market Thesis | `services/cockpit-ui/src/pages/Overview.tsx` | Replace static HTF Thesis with real data |
| Opportunity Detail Context | `services/cockpit-ui/src/pages/OpportunityDetail.tsx` | Add Market Context panel |
| Logs Market Alerts Tab | `services/cockpit-ui/src/pages/Logs.tsx` | Add 3rd tab for market alerts |
| Fixture Runner | `services/market-data/tests/fixture_runner.py` | Offline testing script |
| Rate Limit Tests | `services/market-data/tests/test_rate_limits.py` | Unit tests for RateLimiter |
| Changelog | `docs/changes/2026-01-21_phase3B_complete.md` | Document all changes |

---

## Detailed Instructions for Each Remaining Task

### Task 1: Update Overview.tsx — Real Market Thesis

**File**: `services/cockpit-ui/src/pages/Overview.tsx`

**Current State**: Lines 112-133 contain a static "HTF Thesis" card with hardcoded BTC/ETH bias.

**What to do**:
1. Import `useMarketSnapshots` from `../api/hooks`
2. Call `const { data: marketData } = useMarketSnapshots()`
3. Extract snapshots for BTC-PERP and ETH-PERP
4. Replace the static JSX in the "HTF Thesis" section with:
   - Real regime from `snapshot.regimes.trend` (BULLISH/NEUTRAL/BEARISH mapping)
   - Real funding regime from `snapshot.funding?.regime`
   - Show "Data Unavailable" if no snapshot exists
5. Replace static "Venue Liquidity" section (lines 147-168) with:
   - Import `useMarketStatus` 
   - Show provider status (enabled/disabled, last poll time)

**Example replacement for HTF Thesis**:
```tsx
const btcSnapshot = marketData?.snapshots?.find(s => s.symbol === 'BTC-PERP')
const ethSnapshot = marketData?.snapshots?.find(s => s.symbol === 'ETH-PERP')

// In JSX:
<div className="card border-l-4 border-l-blue-500">
  <h3 className="text-sm font-bold mb-2">HTF Thesis</h3>
  {btcSnapshot ? (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span className="text-gray-400">BTC (1D)</span>
        <span className={regimeColor(btcSnapshot.regimes.trend)}>
          {btcSnapshot.regimes.trend.toUpperCase()}
        </span>
      </div>
      <div className="text-xs text-gray-300">
        Funding: {btcSnapshot.regimes.funding} | OI: {btcSnapshot.regimes.oi}
      </div>
    </div>
  ) : (
    <div className="text-xs text-gray-500 italic">Market data unavailable</div>
  )}
</div>
```

---

### Task 2: Update OpportunityDetail.tsx — Market Context Panel

**File**: `services/cockpit-ui/src/pages/OpportunityDetail.tsx`

**Current State**: No market context. The page shows opportunity details but lacks current market regime info.

**What to do**:
1. Import `useMarketSnapshot` from `../api/hooks`
2. Extract symbol from the opportunity: `const symbol = opportunity.symbol`
3. Call `const { data: marketSnapshot } = useMarketSnapshot('hyperliquid', symbol)`
4. Add a new `<section>` after line 163 (after Evidence Trail) titled "Market Context"
5. Display:
   - Funding regime + current rate
   - OI regime + 24h delta
   - Volume regime
   - Spread (from orderbook)
   - Show REAL/PROXY/UNAVAILABLE badges using `MetricStatusBadge` (copy from Market.tsx)

**Example Market Context panel**:
```tsx
<section className="card bg-gray-900/20 border-gray-800">
  <h3 className="text-sm font-bold mb-3 flex items-center gap-2">
    <Activity size={14} className="text-cyan-400" />
    Market Context
  </h3>
  {marketSnapshot ? (
    <div className="grid grid-cols-2 gap-3 text-xs">
      <div className="bg-gray-900/50 rounded p-2">
        <div className="text-gray-500">Funding Regime</div>
        <div className="font-bold">{marketSnapshot.regimes?.funding || 'N/A'}</div>
      </div>
      <div className="bg-gray-900/50 rounded p-2">
        <div className="text-gray-500">OI Regime</div>
        <div className="font-bold">{marketSnapshot.regimes?.oi || 'N/A'}</div>
      </div>
      <div className="bg-gray-900/50 rounded p-2">
        <div className="text-gray-500">Volume</div>
        <div className="font-bold">{marketSnapshot.regimes?.volume || 'N/A'}</div>
      </div>
      <div className="bg-gray-900/50 rounded p-2">
        <div className="text-gray-500">Spread</div>
        <div className="font-bold">{marketSnapshot.orderbook?.spread_bps?.toFixed(1) || 'N/A'} bps</div>
      </div>
    </div>
  ) : (
    <div className="text-center py-4 text-gray-500 text-xs italic">
      Market context unavailable for {symbol}
    </div>
  )}
</section>
```

---

### Task 3: Update Logs.tsx — Market Alerts Tab

**File**: `services/cockpit-ui/src/pages/Logs.tsx`

**Current State**: Has 2 tabs: "Decisions" and "Orders". Need to add "Market Alerts" tab.

**What to do**:
1. Import `useMarketAlerts` from `../api/hooks`
2. Update `LogTab` type: `type LogTab = 'decisions' | 'orders' | 'alerts'`
3. Add a third tab button after line 39
4. Add the alerts table after line 171 (after orders tab content)
5. Display:
   - Time (formatted from `ts`)
   - Symbol
   - Alert Type (regime_change, extreme, etc.)
   - Metric
   - Previous → New value
   - Context message

**Example Market Alerts tab**:
```tsx
// Add tab button
<button
  onClick={() => setActiveTab('alerts')}
  className={`px-4 py-2 rounded text-sm flex items-center gap-2 ${
    activeTab === 'alerts'
      ? 'bg-blue-600 text-white'
      : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
  }`}
>
  <AlertCircle size={14} />
  Market Alerts
</button>

// Add tab content
{activeTab === 'alerts' && (
  <div className="card">
    <h3 className="text-sm font-medium text-gray-400 mb-4">Market Alerts</h3>
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-800">
            <th className="text-left py-3 px-2 text-gray-500">Time</th>
            <th className="text-left py-3 px-2 text-gray-500">Symbol</th>
            <th className="text-left py-3 px-2 text-gray-500">Type</th>
            <th className="text-left py-3 px-2 text-gray-500">Metric</th>
            <th className="text-left py-3 px-2 text-gray-500">Change</th>
          </tr>
        </thead>
        <tbody>
          {alerts.length === 0 ? (
            <tr>
              <td colSpan={5} className="py-12 text-center text-gray-500">
                No market alerts recorded
              </td>
            </tr>
          ) : (
            alerts.map((alert) => (
              <tr key={alert.id} className="border-b border-gray-800/50">
                <td className="py-2 px-2 font-mono text-xs">
                  {new Date(alert.ts).toLocaleTimeString()}
                </td>
                <td className="py-2 px-2">{alert.symbol}</td>
                <td className="py-2 px-2">{alert.alert_type}</td>
                <td className="py-2 px-2">{alert.metric}</td>
                <td className="py-2 px-2">
                  {alert.previous_value} → {alert.new_value}
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  </div>
)}
```

---

### Task 4: Create Fixture Runner

**File**: `services/market-data/tests/fixture_runner.py` (NEW)

**Purpose**: Load sample payloads from `docs/samples/market/` and push them through the normalizer and snapshotter for offline testing.

```python
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
from pathlib import Path
from datetime import datetime

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.processors import MarketNormalizer, MarketSnapshotter
from app.models import MetricStatus

SAMPLES_DIR = Path(__file__).parent.parent.parent.parent / "docs" / "samples" / "market"


def load_sample(filename: str) -> dict:
    """Load a sample JSON file."""
    with open(SAMPLES_DIR / filename) as f:
        return json.load(f)


def run_fixture_test():
    """Run the fixture through the pipeline."""
    normalizer = MarketNormalizer()
    snapshotter = MarketSnapshotter()

    print("=== Fixture Runner: Market Data Pipeline ===\n")

    # 1. Load Hyperliquid context data
    print("1. Loading hyperliquid_metaAndAssetCtxs.json...")
    hl_context = load_sample("hyperliquid_metaAndAssetCtxs.json")
    print(f"   Loaded {len(hl_context.get('data', []))} assets")

    # 2. Normalize
    print("\n2. Normalizing context data...")
    events = normalizer.normalize_context("hyperliquid", hl_context)
    print(f"   Generated {len(events)} normalized events")

    for evt in events[:3]:  # Show first 3
        print(f"   - {evt.symbol}: funding={evt.value.get('funding_rate', 'N/A')}, oi={evt.value.get('open_interest_usd', 'N/A')}")

    # 3. Process through snapshotter
    print("\n3. Processing events through snapshotter...")
    snapshots = []
    for evt in events:
        snapshot = snapshotter.process_event(evt)
        if snapshot:
            snapshots.append(snapshot)

    print(f"   Generated {len(snapshots)} snapshots")

    # 4. Verify snapshot structure
    print("\n4. Verifying snapshot structure...")
    if snapshots:
        sample = snapshots[0]
        print(f"   Venue: {sample.venue}")
        print(f"   Symbol: {sample.symbol}")
        print(f"   Timestamp: {sample.ts}")
        print(f"   Data Age: {sample.data_age_ms}ms")
        print(f"   Available Metrics: {[m.metric for m in sample.available_metrics]}")
        print(f"   Regimes: {sample.regimes}")

    # 5. Check for truthfulness
    print("\n5. Checking truthfulness (REAL/PROXY/UNAVAILABLE)...")
    for s in snapshots[:3]:
        for m in s.available_metrics:
            status_emoji = "✅" if m.status == MetricStatus.REAL else "⚠️" if m.status == MetricStatus.PROXY else "❌"
            print(f"   {s.symbol} / {m.metric}: {status_emoji} {m.status}")

    print("\n=== Fixture Test Complete ===")
    return len(snapshots) > 0


if __name__ == "__main__":
    success = run_fixture_test()
    sys.exit(0 if success else 1)
```

---

### Task 5: Create Rate Limit Tests

**File**: `services/market-data/tests/test_rate_limits.py` (NEW)

```python
"""
Unit tests for the RateLimiter class.

Verifies:
- Minimum interval enforcement
- Backoff on rate limit errors
- Jitter is applied
- Recovery after success
"""

import pytest
import asyncio
import time
from unittest.mock import patch

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.rate_limiter import RateLimiter, rate_limiters


class TestRateLimiter:

    def test_initial_state(self):
        """RateLimiter starts with backoff_multiplier = 1.0"""
        limiter = RateLimiter(requests_per_minute=60)
        assert limiter.backoff_multiplier == 1.0
        assert limiter.rpm == 60
        assert limiter.min_interval == 1.0  # 60/60

    @pytest.mark.asyncio
    async def test_wait_enforces_interval(self):
        """wait() should enforce minimum interval between requests."""
        limiter = RateLimiter(requests_per_minute=60)
        
        # First request should be immediate
        start = time.time()
        await limiter.wait()
        elapsed1 = time.time() - start
        assert elapsed1 < 0.1  # Nearly instant

        # Second request should wait ~1 second
        start = time.time()
        await limiter.wait()
        elapsed2 = time.time() - start
        assert elapsed2 >= 0.9  # At least ~1 second

    def test_on_rate_limit_increases_backoff(self):
        """on_rate_limit() should double the backoff multiplier."""
        limiter = RateLimiter(requests_per_minute=60)
        assert limiter.backoff_multiplier == 1.0

        limiter.on_rate_limit()
        assert limiter.backoff_multiplier == 2.0

        limiter.on_rate_limit()
        assert limiter.backoff_multiplier == 4.0

    def test_backoff_capped_at_10(self):
        """Backoff multiplier should not exceed 10.0"""
        limiter = RateLimiter(requests_per_minute=60)
        for _ in range(10):
            limiter.on_rate_limit()
        assert limiter.backoff_multiplier == 10.0

    def test_on_success_decreases_backoff(self):
        """on_success() should gradually reduce backoff multiplier."""
        limiter = RateLimiter(requests_per_minute=60)
        limiter.backoff_multiplier = 4.0

        limiter.on_success()
        assert limiter.backoff_multiplier == 3.6  # 4.0 * 0.9

        limiter.on_success()
        assert limiter.backoff_multiplier == 3.24  # 3.6 * 0.9

    def test_backoff_floors_at_1(self):
        """Backoff multiplier should not go below 1.0"""
        limiter = RateLimiter(requests_per_minute=60)
        limiter.backoff_multiplier = 1.1

        for _ in range(10):
            limiter.on_success()
        
        assert limiter.backoff_multiplier == 1.0


class TestGlobalRateLimiters:

    def test_venue_limiters_exist(self):
        """Global rate_limiters should have entries for each venue."""
        assert "hyperliquid" in rate_limiters.limiters
        assert "drift" in rate_limiters.limiters

    def test_status_report(self):
        """status() should return current state of all limiters."""
        status = rate_limiters.status()
        assert isinstance(status, dict)
        assert "hyperliquid" in status
        assert "backoff_multiplier" in status["hyperliquid"]
```

---

### Task 6: Create Changelog

**File**: `docs/changes/2026-01-21_phase3B_complete.md` (NEW)

Document all Phase 3B changes in a single changelog file following the existing format in `docs/changes/`.

---

## How to Resume in Claude Code

When limits reset, paste the following prompt into Claude Code:

```
Resume Phase 3B completion. Read docs/CLAUDE_HANDOFF_PHASE3B.md for full context.

Remaining tasks:
1. Update Overview.tsx with real market thesis (replace static HTF Thesis)
2. Update OpportunityDetail.tsx with Market Context panel
3. Update Logs.tsx with Market Alerts tab
4. Create fixture_runner.py in services/market-data/tests/
5. Create test_rate_limits.py in services/market-data/tests/
6. Create docs/changes/2026-01-21_phase3B_complete.md

Start with task 1 (Overview.tsx) and proceed sequentially.
```

---

## File Locations Quick Reference

| Purpose | Path |
|---------|------|
| Market hooks | `services/cockpit-ui/src/api/hooks/useMarketData.ts` |
| Market types | `services/cockpit-ui/src/api/types.ts` (MarketSnapshot, etc.) |
| Market.tsx (reference) | `services/cockpit-ui/src/pages/Market.tsx` |
| Sample payloads | `docs/samples/market/*.json` |
| Dataflow doc | `docs/architecture/phase3B_dataflow.md` |
| Rate limiter | `services/market-data/app/rate_limiter.py` |

---

## Verification Commands

After completing all tasks:

```bash
# Build and run
docker compose -f ops/compose.full.yml up --build

# Verify market-data service
curl http://localhost:8005/healthz
curl http://localhost:8005/snapshots

# Verify state-api proxy
curl http://localhost:8002/state/market/snapshots
curl http://localhost:8002/state/market/alerts

# Run fixture test
docker compose exec market-data python -m tests.fixture_runner

# Run unit tests
docker compose exec market-data pytest tests/
```

---

*This handoff document is self-contained. Claude Code should be able to complete Phase 3B using only this file.*
