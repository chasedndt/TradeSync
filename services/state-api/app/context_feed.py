"""Free, context-only market enrichment feeds.

These providers enrich the operator dashboard. They are deliberately isolated
from scoring, risk, approvals, and execution. Hyperliquid remains the only
authoritative venue feed and the only future execution venue.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Optional

import httpx

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class CacheEntry:
    payload: Dict[str, Any]
    fetched_at: float


class ContextFeedService:
    """Fetch slow contextual data with independent caches and failures."""

    def __init__(self) -> None:
        self.coingecko_enabled = _env_bool("COINGECKO_CONTEXT_ENABLED", True)
        self.defillama_enabled = _env_bool("DEFILLAMA_CONTEXT_ENABLED", True)
        self.fred_enabled = _env_bool("FRED_CONTEXT_ENABLED", False)
        self.fred_api_key = os.getenv("FRED_API_KEY", "").strip()
        self.fred_series = [
            item.strip()
            for item in os.getenv("FRED_SERIES", "DFF,DTWEXBGS").split(",")
            if item.strip()
        ]
        self.timeout_seconds = float(os.getenv("CONTEXT_FEED_TIMEOUT_SECONDS", "6"))
        self.ttls = {
            "coingecko": int(os.getenv("COINGECKO_CONTEXT_TTL_SECONDS", "300")),
            "defillama": int(os.getenv("DEFILLAMA_CONTEXT_TTL_SECONDS", "900")),
            "fred": int(os.getenv("FRED_CONTEXT_TTL_SECONDS", "3600")),
        }
        self._cache: Dict[str, CacheEntry] = {}
        self._locks = {name: asyncio.Lock() for name in self.ttls}
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout_seconds),
                follow_redirects=True,
                headers={"User-Agent": "TradeSync-ContextFeeds/1.0"},
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _disabled(self, provider: str, reason: str = "disabled_by_configuration") -> Dict[str, Any]:
        return {
            "provider": provider,
            "status": "disabled",
            "source_type": "context_only",
            "execution_authority": False,
            "reason": reason,
            "data": {},
        }

    async def _cached_fetch(
        self,
        provider: str,
        fetcher: Callable[[], Awaitable[Dict[str, Any]]],
        force_refresh: bool,
    ) -> Dict[str, Any]:
        now = time.time()
        cached = self._cache.get(provider)
        if cached and not force_refresh and now - cached.fetched_at < self.ttls[provider]:
            return self._format(provider, cached, cached=True)

        async with self._locks[provider]:
            now = time.time()
            cached = self._cache.get(provider)
            if cached and not force_refresh and now - cached.fetched_at < self.ttls[provider]:
                return self._format(provider, cached, cached=True)

            try:
                payload = await fetcher()
                entry = CacheEntry(payload=payload, fetched_at=time.time())
                self._cache[provider] = entry
                return self._format(provider, entry, cached=False)
            except Exception as exc:
                logger.warning("Context provider %s failed: %s", provider, type(exc).__name__)
                if cached:
                    result = self._format(provider, cached, cached=True)
                    result.update(status="degraded", error="provider_refresh_failed")
                    return result
                return {
                    "provider": provider,
                    "status": "unavailable",
                    "source_type": "context_only",
                    "execution_authority": False,
                    "cached": False,
                    "stale": True,
                    "age_seconds": None,
                    "fetched_at": None,
                    "ttl_seconds": self.ttls[provider],
                    "error": "provider_fetch_failed",
                    "data": {},
                }

    def _format(self, provider: str, entry: CacheEntry, cached: bool) -> Dict[str, Any]:
        age = max(0.0, time.time() - entry.fetched_at)
        return {
            "provider": provider,
            "status": "healthy" if age <= self.ttls[provider] else "stale",
            "source_type": "context_only",
            "execution_authority": False,
            "cached": cached,
            "stale": age > self.ttls[provider],
            "age_seconds": round(age, 3),
            "fetched_at": datetime.fromtimestamp(entry.fetched_at, timezone.utc).isoformat(),
            "ttl_seconds": self.ttls[provider],
            "data": entry.payload,
        }

    async def _fetch_coingecko(self) -> Dict[str, Any]:
        client = await self._get_client()
        response = await client.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={
                "ids": "bitcoin,ethereum,solana",
                "vs_currencies": "usd",
                "include_24hr_change": "true",
                "include_last_updated_at": "true",
            },
        )
        response.raise_for_status()
        raw = response.json()
        symbols = {"bitcoin": "BTC", "ethereum": "ETH", "solana": "SOL"}
        assets = {}
        for asset_id, symbol in symbols.items():
            item = raw.get(asset_id) or {}
            if "usd" not in item:
                continue
            assets[symbol] = {
                "price_usd": item["usd"],
                "change_24h_pct": item.get("usd_24h_change"),
                "observed_at": item.get("last_updated_at"),
            }
        if not assets:
            raise ValueError("CoinGecko response contained no tracked assets")
        return {"metric_family": "aggregate_spot_reference", "assets": assets}

    async def _fetch_defillama(self) -> Dict[str, Any]:
        client = await self._get_client()
        response = await client.get("https://api.llama.fi/tvl/hyperliquid")
        response.raise_for_status()
        return {
            "metric_family": "protocol_context",
            "protocol": "Hyperliquid",
            "tvl_usd": float(response.json()),
        }

    async def _fetch_fred(self) -> Dict[str, Any]:
        if not self.fred_api_key:
            raise RuntimeError("FRED API key is not configured")
        client = await self._get_client()
        values: Dict[str, Any] = {}
        for series_id in self.fred_series:
            response = await client.get(
                "https://api.stlouisfed.org/fred/series/observations",
                params={
                    "series_id": series_id,
                    "api_key": self.fred_api_key,
                    "file_type": "json",
                    "sort_order": "desc",
                    "limit": "1",
                },
            )
            response.raise_for_status()
            observations = response.json().get("observations") or []
            if observations:
                latest = observations[0]
                values[series_id] = {"value": latest.get("value"), "date": latest.get("date")}
        return {"metric_family": "macro_reference", "series": values}

    async def fetch_overview(self, force_refresh: bool = False) -> Dict[str, Any]:
        tasks = []
        names = []

        if self.coingecko_enabled:
            names.append("coingecko")
            tasks.append(self._cached_fetch("coingecko", self._fetch_coingecko, force_refresh))
        if self.defillama_enabled:
            names.append("defillama")
            tasks.append(self._cached_fetch("defillama", self._fetch_defillama, force_refresh))
        if self.fred_enabled and self.fred_api_key:
            names.append("fred")
            tasks.append(self._cached_fetch("fred", self._fetch_fred, force_refresh))

        results = await asyncio.gather(*tasks) if tasks else []
        providers = {name: result for name, result in zip(names, results)}
        if not self.coingecko_enabled:
            providers["coingecko"] = self._disabled("coingecko")
        if not self.defillama_enabled:
            providers["defillama"] = self._disabled("defillama")
        if not self.fred_enabled:
            providers["fred"] = self._disabled("fred")
        elif not self.fred_api_key:
            providers["fred"] = self._disabled("fred", "free_api_key_not_configured")

        return {
            "role": "context_only",
            "authoritative_market_source": "hyperliquid",
            "execution_venue": "hyperliquid",
            "execution_authority": False,
            "providers": providers,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def get_status(self) -> Dict[str, Any]:
        return {
            "role": "context_only",
            "execution_authority": False,
            "providers": {
                "coingecko": {"enabled": self.coingecko_enabled, "ttl_seconds": self.ttls["coingecko"]},
                "defillama": {"enabled": self.defillama_enabled, "ttl_seconds": self.ttls["defillama"]},
                "fred": {
                    "enabled": self.fred_enabled,
                    "configured": bool(self.fred_api_key),
                    "ttl_seconds": self.ttls["fred"],
                    "series": self.fred_series,
                },
            },
        }


context_feed = ContextFeedService()
