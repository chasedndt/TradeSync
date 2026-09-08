"""A read must not block on three external feeds."""

from __future__ import annotations

import asyncio
import time

import pytest

from _service_import import load_service_module

macro_feed_module = load_service_module("state_api_app", "state-api", "macro_feed")
MacroFeedService = macro_feed_module.MacroFeedService
MacroHeadline = macro_feed_module.MacroHeadline


def headline(title: str = "something happened"):
    return MacroHeadline(
        title=title, source="test", category="macro", url="https://example.invalid/x"
    )


@pytest.mark.asyncio
async def test_a_stale_cache_is_served_immediately_and_refreshed_behind_it() -> None:
    """The failure this prevents: a dashboard panel hanging for seconds, on a
    schedule, for news.

    Before this, the first request after the TTL expired paid the full external
    fetch cost and every concurrent request queued behind it on the lock.
    """
    service = MacroFeedService()
    service.cache = [headline("cached")]
    service.cache_updated_at = time.time() - macro_feed_module.CACHE_TTL_SECONDS - 1
    assert service.is_stale()

    fetched = asyncio.Event()

    async def slow_refresh(force_refresh: bool = False):
        fetched.set()
        await asyncio.sleep(30)  # would blow any caller's timeout

    service._refresh_quietly = lambda: slow_refresh()  # type: ignore[assignment]

    started = time.monotonic()
    result = await service.fetch_headlines()
    elapsed = time.monotonic() - started

    assert result[0].title == "cached"
    assert elapsed < 0.5, "a stale read waited on the network"

    # And the refresh actually started rather than the staleness being ignored.
    await asyncio.wait_for(fetched.wait(), timeout=1.0)
    if service._refresh_task:
        service._refresh_task.cancel()


@pytest.mark.asyncio
async def test_a_fresh_cache_starts_no_refresh() -> None:
    service = MacroFeedService()
    service.cache = [headline()]
    service.cache_updated_at = time.time()

    await service.fetch_headlines()
    assert service._refresh_task is None
    assert service.is_stale() is False


@pytest.mark.asyncio
async def test_ten_stale_readers_start_one_refresh_not_ten() -> None:
    service = MacroFeedService()
    service.cache = [headline()]
    service.cache_updated_at = time.time() - macro_feed_module.CACHE_TTL_SECONDS - 1

    started = 0

    async def counted():
        nonlocal started
        started += 1
        await asyncio.sleep(5)

    service._refresh_quietly = counted  # type: ignore[assignment]

    await asyncio.gather(*(service.fetch_headlines() for _ in range(10)))
    await asyncio.sleep(0)
    assert started == 1, f"{started} refreshes started"
    if service._refresh_task:
        service._refresh_task.cancel()


@pytest.mark.asyncio
async def test_a_failed_background_refresh_leaves_the_stale_cache_in_place() -> None:
    """Nobody is waiting on it, so it must not become an unhandled exception —
    and it must not empty the cache it failed to replace."""
    service = MacroFeedService()
    service.cache = [headline("kept")]
    service.cache_updated_at = time.time() - 10_000

    async def boom(force_refresh: bool = False):
        raise RuntimeError("feed unreachable")

    service.fetch_headlines = boom  # type: ignore[assignment]
    await service._refresh_quietly()  # must not raise
    assert service.cache[0].title == "kept"


def test_the_status_says_whether_what_you_read_was_stale() -> None:
    """A reader cannot tell from the headlines. Serving stale is fine; serving
    it silently is not."""
    service = MacroFeedService()
    assert service.get_status()["stale"] is True  # nothing cached at all

    service.cache = [headline()]
    service.cache_updated_at = time.time()
    fresh = service.get_status()
    assert fresh["stale"] is False
    assert fresh["cache_age_seconds"] < 1

    service.cache_updated_at = time.time() - macro_feed_module.CACHE_TTL_SECONDS - 1
    assert service.get_status()["stale"] is True
