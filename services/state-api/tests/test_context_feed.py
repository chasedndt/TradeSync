import asyncio
from unittest.mock import AsyncMock

from app.context_feed import ContextFeedService


def test_context_feeds_are_context_only_and_cached():
    service = ContextFeedService()
    service.coingecko_enabled = True
    service.defillama_enabled = True
    service.fred_enabled = False
    service._fetch_coingecko = AsyncMock(
        return_value={"metric_family": "aggregate_spot_reference", "assets": {"BTC": {"price_usd": 1}}}
    )
    service._fetch_defillama = AsyncMock(
        return_value={"metric_family": "protocol_context", "protocol": "Hyperliquid", "tvl_usd": 2}
    )

    first = asyncio.run(service.fetch_overview())
    second = asyncio.run(service.fetch_overview())

    assert first["authoritative_market_source"] == "hyperliquid"
    assert first["execution_venue"] == "hyperliquid"
    assert first["execution_authority"] is False
    assert first["providers"]["coingecko"]["source_type"] == "context_only"
    assert first["providers"]["defillama"]["status"] == "healthy"
    assert first["providers"]["fred"]["status"] == "disabled"
    assert second["providers"]["coingecko"]["cached"] is True
    service._fetch_coingecko.assert_awaited_once()
    service._fetch_defillama.assert_awaited_once()


def test_provider_failure_is_isolated():
    service = ContextFeedService()
    service.coingecko_enabled = True
    service.defillama_enabled = True
    service.fred_enabled = False
    service._fetch_coingecko = AsyncMock(side_effect=RuntimeError("rate limited"))
    service._fetch_defillama = AsyncMock(
        return_value={"metric_family": "protocol_context", "protocol": "Hyperliquid", "tvl_usd": 2}
    )

    result = asyncio.run(service.fetch_overview())

    assert result["providers"]["coingecko"]["status"] == "unavailable"
    assert result["providers"]["defillama"]["status"] == "healthy"
    assert result["execution_authority"] is False
