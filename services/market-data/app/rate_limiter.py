"""
Rate limiter with exponential backoff and jitter.

Implements the strategy from docs/providers/MARKET_PROVIDER_MATRIX.md
"""

import time
import random
import asyncio
import logging
from typing import Dict

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Rate limiter for API requests with backoff and jitter.

    Features:
    - Per-minute rate limiting
    - Exponential backoff on rate limit errors
    - Random jitter to prevent thundering herd
    - Automatic recovery after successful requests
    """

    def __init__(self, venue: str, requests_per_minute: int = 60):
        self.venue = venue
        self.rpm = requests_per_minute
        self.min_interval = 60.0 / requests_per_minute
        self.backoff_multiplier = 1.0
        self.last_request = 0.0
        self.consecutive_errors = 0
        self.max_backoff = 10.0  # Max 10x slowdown

    async def acquire(self):
        """
        Wait until we can make a request.
        Call this before each API request.
        """
        elapsed = time.time() - self.last_request
        wait_time = (self.min_interval * self.backoff_multiplier) - elapsed

        if wait_time > 0:
            # Add jitter: 0-20% of min interval
            jitter = random.uniform(0, 0.2 * self.min_interval)
            total_wait = wait_time + jitter
            logger.debug(
                f"[{self.venue}] Rate limiting: waiting {total_wait:.2f}s "
                f"(backoff={self.backoff_multiplier:.1f}x)"
            )
            await asyncio.sleep(total_wait)

        self.last_request = time.time()

    def on_success(self):
        """Call after successful request. Reduces backoff."""
        self.consecutive_errors = 0
        if self.backoff_multiplier > 1.0:
            self.backoff_multiplier = max(1.0, self.backoff_multiplier * 0.9)
            logger.debug(
                f"[{self.venue}] Reduced backoff to {self.backoff_multiplier:.1f}x"
            )

    def on_rate_limit(self):
        """Call when rate limited. Increases backoff exponentially."""
        self.consecutive_errors += 1
        old_backoff = self.backoff_multiplier
        self.backoff_multiplier = min(self.max_backoff, self.backoff_multiplier * 2.0)
        logger.warning(
            f"[{self.venue}] Rate limited! Backoff increased: "
            f"{old_backoff:.1f}x -> {self.backoff_multiplier:.1f}x "
            f"(consecutive errors: {self.consecutive_errors})"
        )

    def on_error(self):
        """Call on non-rate-limit errors. Mild backoff."""
        self.consecutive_errors += 1
        if self.consecutive_errors >= 3:
            self.backoff_multiplier = min(self.max_backoff, self.backoff_multiplier * 1.5)
            logger.warning(
                f"[{self.venue}] Multiple errors, backoff: {self.backoff_multiplier:.1f}x"
            )

    @property
    def current_rpm(self) -> float:
        """Current effective requests per minute."""
        return self.rpm / self.backoff_multiplier

    def status(self) -> Dict:
        """Get current status."""
        return {
            "venue": self.venue,
            "base_rpm": self.rpm,
            "current_rpm": round(self.current_rpm, 1),
            "backoff_multiplier": round(self.backoff_multiplier, 2),
            "consecutive_errors": self.consecutive_errors,
            "last_request": self.last_request
        }


class RateLimiterRegistry:
    """Registry of rate limiters per venue."""

    def __init__(self):
        self._limiters: Dict[str, RateLimiter] = {}

    def get(self, venue: str, rpm: int = 60) -> RateLimiter:
        """Get or create rate limiter for venue."""
        if venue not in self._limiters:
            self._limiters[venue] = RateLimiter(venue, rpm)
        return self._limiters[venue]

    def status(self) -> Dict[str, Dict]:
        """Get status of all limiters."""
        return {venue: limiter.status() for venue, limiter in self._limiters.items()}


# Default rate limits per venue (requests per minute)
VENUE_RATE_LIMITS = {
    "hyperliquid": 120,  # Conservative
    "drift": 60,         # Conservative
}


# Singleton registry
rate_limiters = RateLimiterRegistry()


def get_limiter(venue: str) -> RateLimiter:
    """Get rate limiter for venue."""
    rpm = VENUE_RATE_LIMITS.get(venue, 60)
    return rate_limiters.get(venue, rpm)
