"""
Base provider interface for market data sources.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger(__name__)


class BaseProvider(ABC):
    """Abstract base class for market data providers."""

    def __init__(self, venue: str):
        self.venue = venue
        self._enabled = True

    @property
    def enabled(self) -> bool:
        return self._enabled

    def disable(self):
        """Disable this provider."""
        self._enabled = False
        logger.warning(f"Provider {self.venue} disabled")

    def enable(self):
        """Enable this provider."""
        self._enabled = True
        logger.info(f"Provider {self.venue} enabled")

    @abstractmethod
    async def fetch_context(self, symbols: List[str]) -> Dict[str, Any]:
        """
        Fetch main context data (funding, OI, volume, mark price).

        Args:
            symbols: List of canonical symbols (e.g., ["BTC-PERP", "ETH-PERP"])

        Returns:
            Dict with raw data keyed by symbol
        """
        pass

    @abstractmethod
    async def fetch_orderbook(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Fetch L2 orderbook for a symbol.

        Args:
            symbol: Canonical symbol (e.g., "BTC-PERP")

        Returns:
            Dict with bids, asks, spread info
        """
        pass

    @abstractmethod
    async def fetch_funding_history(
        self,
        symbol: str,
        start_time: int
    ) -> List[Dict[str, Any]]:
        """
        Fetch historical funding rates.

        Args:
            symbol: Canonical symbol
            start_time: Unix timestamp (ms) to start from

        Returns:
            List of funding rate records
        """
        pass

    @abstractmethod
    def normalize_symbol(self, venue_symbol: str) -> str:
        """Convert venue symbol to canonical format."""
        pass

    @abstractmethod
    def denormalize_symbol(self, canonical_symbol: str) -> str:
        """Convert canonical symbol to venue format."""
        pass

    def get_supported_metrics(self) -> List[str]:
        """Return list of metrics this provider supports."""
        return ["funding", "oi", "volume", "orderbook"]
