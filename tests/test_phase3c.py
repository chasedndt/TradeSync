"""
Phase 3C Tests: Market Microstructure, Enhanced Scoring, Risk Guardian, Macro Feed

Run with: pytest tests/test_phase3c.py -v
Requires: docker compose -f ops/compose.full.yml up -d
"""

import httpx
import pytest
import json

STATE_API_URL = "http://localhost:8000"
MARKET_DATA_URL = "http://localhost:8005"


# === Microstructure Tests ===

@pytest.mark.asyncio
async def test_market_snapshot_includes_microstructure():
    """Verify market snapshot response includes microstructure field."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{MARKET_DATA_URL}/snapshots")
        assert resp.status_code == 200
        data = resp.json()

        # Check if snapshots exist
        snapshots = data.get("snapshots", [])
        if len(snapshots) > 0:
            snapshot = snapshots[0]
            # Microstructure should be present (may be None if orderbook unavailable)
            assert "microstructure" in snapshot or snapshot.get("orderbook") is not None


@pytest.mark.asyncio
async def test_microstructure_fields_structure():
    """Verify microstructure data has expected fields when present."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{MARKET_DATA_URL}/snapshots")
        if resp.status_code != 200:
            pytest.skip("Market data service not available")

        data = resp.json()
        snapshots = data.get("snapshots", [])

        for snapshot in snapshots:
            micro = snapshot.get("microstructure")
            if micro:
                # Required fields
                assert "spread_bps" in micro
                assert "mid_price" in micro
                assert "liquidity_score" in micro
                assert "depth_usd" in micro
                assert "impact_est_bps" in micro

                # Depth should have BPS thresholds
                depth = micro["depth_usd"]
                assert isinstance(depth, dict)

                # Impact should have USD size keys
                impact = micro["impact_est_bps"]
                assert isinstance(impact, dict)

                # Liquidity score should be 0-1
                assert 0 <= micro["liquidity_score"] <= 1

                print(f"Microstructure for {snapshot.get('symbol')}: "
                      f"spread={micro['spread_bps']:.1f}bps, "
                      f"liquidity={micro['liquidity_score']:.2f}")


# === Enhanced Scoring Tests ===

@pytest.mark.asyncio
async def test_opportunity_includes_confluence():
    """Verify opportunity response includes confluence scoring data."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{STATE_API_URL}/state/opportunities?limit=10")
        assert resp.status_code == 200
        data = resp.json()

        # Note: confluence is optional and may not be present on all opportunities
        # But the field should exist in the schema
        for opp in data:
            # Schema should support confluence field
            # It may be null/None if the opportunity was created before Phase 3C
            if "confluence" in opp and opp["confluence"]:
                confluence = opp["confluence"]

                # Check score_breakdown structure
                if "score_breakdown" in confluence:
                    breakdown = confluence["score_breakdown"]
                    assert "alpha" in breakdown
                    assert "final_score" in breakdown
                    print(f"Opportunity {opp['id'][:8]} confluence: "
                          f"alpha={breakdown.get('alpha')}, "
                          f"final={breakdown.get('final_score')}")


# === Risk Guardian Tests ===

@pytest.mark.asyncio
async def test_risk_limits_endpoint():
    """Verify risk limits endpoint returns microstructure thresholds."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{STATE_API_URL}/state/risk/limits")
        assert resp.status_code == 200
        data = resp.json()

        # Standard risk limits
        assert "max_leverage" in data
        assert "min_quality" in data
        assert "blacklist" in data


@pytest.mark.asyncio
async def test_preview_includes_microstructure_checks():
    """Verify preview endpoint performs microstructure-based risk checks."""
    async with httpx.AsyncClient() as client:
        # First get an opportunity to preview
        opps_resp = await client.get(f"{STATE_API_URL}/state/opportunities?status=new&limit=1")
        if opps_resp.status_code != 200 or not opps_resp.json():
            pytest.skip("No opportunities available for preview test")

        opp = opps_resp.json()[0]

        # Request preview
        preview_req = {
            "opportunity_id": opp["id"],
            "size_usd": 1000.0,
            "venue": "hyperliquid"
        }

        resp = await client.post(f"{STATE_API_URL}/actions/preview", json=preview_req)
        assert resp.status_code == 200
        data = resp.json()

        # Check response structure
        assert "risk_verdict" in data
        assert "allowed" in data["risk_verdict"]
        assert "reason" in data["risk_verdict"]

        # Check for reason_code (Phase 3C addition)
        if "reason_code" in data["risk_verdict"]:
            reason_code = data["risk_verdict"]["reason_code"]
            # Valid Phase 3C reason codes
            valid_codes = [
                "OK", "EXEC_DISABLED", "DNT", "STALE_DATA", "EXPIRED",
                "DUPLICATE", "COOLDOWN", "LIMIT_DAILY", "LIMIT_POSITIONS",
                "MIN_QUALITY", "MIN_SIZE", "MAX_LEVERAGE",
                # Phase 3C additions
                "SPREAD_TOO_WIDE", "SLIPPAGE_TOO_HIGH", "DEPTH_TOO_THIN",
                "LIQUIDITY_TOO_LOW", "MARGIN_STRESS", "EXPOSURE_TOO_HIGH"
            ]
            assert reason_code in valid_codes, f"Unknown reason code: {reason_code}"
            print(f"Preview verdict: allowed={data['risk_verdict']['allowed']}, "
                  f"reason_code={reason_code}")


# === Macro Feed Tests ===

@pytest.mark.asyncio
async def test_macro_headlines_endpoint():
    """Verify macro headlines endpoint returns expected structure."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{STATE_API_URL}/state/macro/headlines")
        assert resp.status_code == 200
        data = resp.json()

        # Check response structure
        assert "headlines" in data
        assert "status" in data
        assert "cached" in data
        assert "ts" in data

        # Check status structure
        status = data["status"]
        assert "sources_configured" in status
        assert "headlines_cached" in status

        print(f"Macro feed: {len(data['headlines'])} headlines, "
              f"{status['sources_configured']} sources")


@pytest.mark.asyncio
async def test_macro_headlines_structure():
    """Verify macro headline objects have expected fields."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{STATE_API_URL}/state/macro/headlines?limit=5")
        assert resp.status_code == 200
        data = resp.json()

        for headline in data["headlines"]:
            assert "title" in headline
            assert "source" in headline
            assert "category" in headline
            assert "url" in headline

            # Optional fields
            if "sentiment" in headline and headline["sentiment"]:
                assert headline["sentiment"] in ["bullish", "bearish", "neutral"]

            print(f"Headline: [{headline.get('sentiment', 'unknown')}] {headline['title'][:50]}...")


@pytest.mark.asyncio
async def test_macro_headlines_filtering():
    """Verify macro headlines can be filtered by category."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{STATE_API_URL}/state/macro/headlines?category=crypto")
        assert resp.status_code == 200
        data = resp.json()

        for headline in data["headlines"]:
            assert headline["category"] == "crypto"


@pytest.mark.asyncio
async def test_macro_status_endpoint():
    """Verify macro status endpoint returns service status."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{STATE_API_URL}/state/macro/status")
        assert resp.status_code == 200
        data = resp.json()

        assert "sources_configured" in data
        assert "sources" in data
        assert isinstance(data["sources"], list)


# === Integration Tests ===

@pytest.mark.asyncio
async def test_full_flow_with_microstructure():
    """Test full opportunity flow with microstructure data."""
    async with httpx.AsyncClient() as client:
        # 1. Get opportunities
        opps_resp = await client.get(f"{STATE_API_URL}/state/opportunities?status=new&limit=1")
        assert opps_resp.status_code == 200

        opps = opps_resp.json()
        if not opps:
            pytest.skip("No opportunities available")

        opp = opps[0]
        symbol = opp["symbol"]

        # 2. Get market snapshot for same symbol
        market_resp = await client.get(f"{MARKET_DATA_URL}/snapshot/hyperliquid/{symbol}")

        # 3. Get evidence trail
        evidence_resp = await client.get(f"{STATE_API_URL}/state/evidence?opportunity_id={opp['id']}")
        assert evidence_resp.status_code == 200

        # 4. Preview with microstructure awareness
        preview_req = {
            "opportunity_id": opp["id"],
            "size_usd": 500.0,
            "venue": "hyperliquid"
        }
        preview_resp = await client.post(f"{STATE_API_URL}/actions/preview", json=preview_req)
        assert preview_resp.status_code == 200

        preview = preview_resp.json()
        print(f"\nFull flow test for {symbol}:")
        print(f"  Opportunity quality: {opp['quality']}")
        print(f"  Preview allowed: {preview['risk_verdict']['allowed']}")
        print(f"  Reason: {preview['risk_verdict']['reason']}")
