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
import sys
from pathlib import Path
from unittest.mock import patch

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.rate_limiter import RateLimiter, RateLimiterRegistry, rate_limiters, get_limiter


class TestRateLimiter:
    """Tests for individual RateLimiter instance."""

    def test_initial_state(self):
        """RateLimiter starts with backoff_multiplier = 1.0"""
        limiter = RateLimiter("test", requests_per_minute=60)
        assert limiter.backoff_multiplier == 1.0
        assert limiter.rpm == 60
        assert limiter.min_interval == 1.0  # 60/60
        assert limiter.venue == "test"
        assert limiter.consecutive_errors == 0

    def test_min_interval_calculation(self):
        """Min interval should be 60/rpm."""
        limiter_60 = RateLimiter("test", requests_per_minute=60)
        assert limiter_60.min_interval == 1.0

        limiter_120 = RateLimiter("test", requests_per_minute=120)
        assert limiter_120.min_interval == 0.5

        limiter_30 = RateLimiter("test", requests_per_minute=30)
        assert limiter_30.min_interval == 2.0

    @pytest.mark.asyncio
    async def test_acquire_first_request_immediate(self):
        """First request should be immediate (no wait)."""
        limiter = RateLimiter("test", requests_per_minute=60)
        limiter.last_request = 0  # Reset to ensure no previous request

        start = time.time()
        await limiter.acquire()
        elapsed = time.time() - start

        # Should be nearly instant (less than 100ms)
        assert elapsed < 0.1

    @pytest.mark.asyncio
    async def test_acquire_enforces_interval(self):
        """Second request should wait for min interval."""
        # Use high RPM for faster test
        limiter = RateLimiter("test", requests_per_minute=600)  # 0.1s interval

        # First request
        await limiter.acquire()

        # Second request should wait ~0.1s (plus jitter up to 0.02s)
        start = time.time()
        await limiter.acquire()
        elapsed = time.time() - start

        # Should wait approximately 0.1s (with some tolerance for jitter)
        assert elapsed >= 0.08  # Allow some margin
        assert elapsed < 0.15   # But not too long

    def test_on_rate_limit_increases_backoff(self):
        """on_rate_limit() should double the backoff multiplier."""
        limiter = RateLimiter("test", requests_per_minute=60)
        assert limiter.backoff_multiplier == 1.0

        limiter.on_rate_limit()
        assert limiter.backoff_multiplier == 2.0
        assert limiter.consecutive_errors == 1

        limiter.on_rate_limit()
        assert limiter.backoff_multiplier == 4.0
        assert limiter.consecutive_errors == 2

        limiter.on_rate_limit()
        assert limiter.backoff_multiplier == 8.0
        assert limiter.consecutive_errors == 3

    def test_backoff_capped_at_max(self):
        """Backoff multiplier should not exceed max_backoff (10.0)."""
        limiter = RateLimiter("test", requests_per_minute=60)

        # Trigger many rate limits
        for _ in range(10):
            limiter.on_rate_limit()

        assert limiter.backoff_multiplier == 10.0  # max_backoff

        # Should not exceed even with more calls
        limiter.on_rate_limit()
        assert limiter.backoff_multiplier == 10.0

    def test_on_success_decreases_backoff(self):
        """on_success() should gradually reduce backoff multiplier."""
        limiter = RateLimiter("test", requests_per_minute=60)
        limiter.backoff_multiplier = 4.0
        limiter.consecutive_errors = 5

        limiter.on_success()
        assert limiter.backoff_multiplier == 3.6  # 4.0 * 0.9
        assert limiter.consecutive_errors == 0  # Reset

        limiter.on_success()
        assert abs(limiter.backoff_multiplier - 3.24) < 0.01  # 3.6 * 0.9

    def test_backoff_floors_at_1(self):
        """Backoff multiplier should not go below 1.0."""
        limiter = RateLimiter("test", requests_per_minute=60)
        limiter.backoff_multiplier = 1.1

        # Multiple successes
        for _ in range(20):
            limiter.on_success()

        assert limiter.backoff_multiplier == 1.0

    def test_on_error_mild_backoff_after_threshold(self):
        """on_error() should apply mild backoff after 3 consecutive errors."""
        limiter = RateLimiter("test", requests_per_minute=60)

        # First two errors don't change backoff
        limiter.on_error()
        assert limiter.backoff_multiplier == 1.0
        limiter.on_error()
        assert limiter.backoff_multiplier == 1.0

        # Third error triggers 1.5x backoff
        limiter.on_error()
        assert limiter.backoff_multiplier == 1.5

        # Fourth error increases further
        limiter.on_error()
        assert abs(limiter.backoff_multiplier - 2.25) < 0.01  # 1.5 * 1.5

    def test_current_rpm(self):
        """current_rpm should reflect backoff."""
        limiter = RateLimiter("test", requests_per_minute=120)
        assert limiter.current_rpm == 120.0

        limiter.backoff_multiplier = 2.0
        assert limiter.current_rpm == 60.0

        limiter.backoff_multiplier = 4.0
        assert limiter.current_rpm == 30.0

    def test_status_report(self):
        """status() should return current state dict."""
        limiter = RateLimiter("hyperliquid", requests_per_minute=120)
        limiter.backoff_multiplier = 2.0
        limiter.consecutive_errors = 3

        status = limiter.status()

        assert status["venue"] == "hyperliquid"
        assert status["base_rpm"] == 120
        assert status["current_rpm"] == 60.0
        assert status["backoff_multiplier"] == 2.0
        assert status["consecutive_errors"] == 3
        assert "last_request" in status


class TestRateLimiterRegistry:
    """Tests for RateLimiterRegistry."""

    def test_creates_new_limiter(self):
        """get() should create new limiter if not exists."""
        registry = RateLimiterRegistry()

        limiter = registry.get("test_venue", rpm=100)

        assert limiter.venue == "test_venue"
        assert limiter.rpm == 100

    def test_returns_existing_limiter(self):
        """get() should return same instance for same venue."""
        registry = RateLimiterRegistry()

        limiter1 = registry.get("test_venue", rpm=100)
        limiter2 = registry.get("test_venue", rpm=200)  # Different rpm ignored

        assert limiter1 is limiter2
        assert limiter1.rpm == 100  # Original rpm preserved

    def test_status_all_limiters(self):
        """status() should return status for all limiters."""
        registry = RateLimiterRegistry()
        registry.get("venue_a", rpm=60)
        registry.get("venue_b", rpm=120)

        status = registry.status()

        assert "venue_a" in status
        assert "venue_b" in status
        assert status["venue_a"]["base_rpm"] == 60
        assert status["venue_b"]["base_rpm"] == 120


class TestGlobalRateLimiters:
    """Tests for global rate_limiters instance."""

    def test_get_limiter_hyperliquid(self):
        """get_limiter should return configured limiter for hyperliquid."""
        limiter = get_limiter("hyperliquid")
        assert limiter.venue == "hyperliquid"
        assert limiter.rpm == 120  # From VENUE_RATE_LIMITS

    def test_get_limiter_drift(self):
        """get_limiter should return configured limiter for drift."""
        limiter = get_limiter("drift")
        assert limiter.venue == "drift"
        assert limiter.rpm == 60  # From VENUE_RATE_LIMITS

    def test_get_limiter_unknown_venue(self):
        """get_limiter should use default 60 rpm for unknown venues."""
        limiter = get_limiter("unknown_venue")
        assert limiter.venue == "unknown_venue"
        assert limiter.rpm == 60  # Default

    def test_global_registry_status(self):
        """Global rate_limiters.status() should work."""
        # Ensure at least one limiter exists
        get_limiter("hyperliquid")

        status = rate_limiters.status()

        assert isinstance(status, dict)
        assert "hyperliquid" in status


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
