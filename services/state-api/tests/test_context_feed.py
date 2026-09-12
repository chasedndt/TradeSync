import asyncio
from unittest.mock import AsyncMock

from app.context_feed import ContextFeedService


def test_context_feeds_are_context_only_and_cached():
    service = ContextFeedService()
    service.coingecko_enabled = True
    service.defillama_enabled = True
    service.fred_enabled = False
    service.calendar_enabled = False
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
    service.calendar_enabled = False
    service._fetch_coingecko = AsyncMock(side_effect=RuntimeError("rate limited"))
    service._fetch_defillama = AsyncMock(
        return_value={"metric_family": "protocol_context", "protocol": "Hyperliquid", "tvl_usd": 2}
    )

    result = asyncio.run(service.fetch_overview())

    assert result["providers"]["coingecko"]["status"] == "unavailable"
    assert result["providers"]["defillama"]["status"] == "healthy"
    assert result["execution_authority"] is False


def test_a_failed_provider_is_not_asked_again_until_the_hold_expires():
    """The Cockpit polls the overview every minute; a rate-limiting feed must
    not be re-asked on every poll, or a short 429 becomes a long one."""
    service = ContextFeedService()
    service.coingecko_enabled = False
    service.defillama_enabled = False
    service.fred_enabled = False
    service.calendar_enabled = True
    service.failure_hold_seconds = 900
    service._fetch_calendar = AsyncMock(side_effect=RuntimeError("429"))

    first = asyncio.run(service.fetch_overview())
    second = asyncio.run(service.fetch_overview())

    assert first["providers"]["calendar"]["status"] == "unavailable"
    assert second["providers"]["calendar"]["error"] == "provider_fetch_failed_recently"
    assert 0 < second["providers"]["calendar"]["retry_in_seconds"] <= 900
    service._fetch_calendar.assert_awaited_once()

    # Once the hold has passed, it is asked again — and a success clears it.
    service.failure_hold_seconds = 0
    service._fetch_calendar = AsyncMock(return_value={"metric_family": "economic_calendar", "events": []})
    third = asyncio.run(service.fetch_overview())
    assert third["providers"]["calendar"]["status"] == "healthy"
    assert "calendar" not in service._failed_at
