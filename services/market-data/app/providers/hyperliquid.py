"""
Hyperliquid market data provider.

API Documentation: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint
"""

import httpx
import logging
import time
from typing import Dict, List, Any, Optional

from .base import BaseProvider
from ..rate_limiter import get_limiter

logger = logging.getLogger(__name__)

HYPERLIQUID_API_URL = "https://api.hyperliquid.xyz/info"


class HyperliquidProvider(BaseProvider):
    """Hyperliquid market data provider."""

    def __init__(self):
        super().__init__("hyperliquid")
        self.api_url = HYPERLIQUID_API_URL
        self.limiter = get_limiter("hyperliquid")

        # Symbol mappings
        self._symbol_map = {
            "BTC": "BTC-PERP",
            "ETH": "ETH-PERP",
            "SOL": "SOL-PERP",
        }
        self._reverse_map = {v: k for k, v in self._symbol_map.items()}

    def normalize_symbol(self, venue_symbol: str) -> str:
        """Convert HL symbol (e.g., 'BTC') to canonical (e.g., 'BTC-PERP')."""
        return self._symbol_map.get(venue_symbol.upper(), f"{venue_symbol.upper()}-PERP")

    def denormalize_symbol(self, canonical_symbol: str) -> str:
        """Convert canonical symbol to HL format."""
        return self._reverse_map.get(canonical_symbol, canonical_symbol.replace("-PERP", ""))

    async def _request(self, payload: Dict[str, Any]) -> Any:
        """Make rate-limited request to Hyperliquid API."""
        await self.limiter.acquire()

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.api_url,
                    json=payload,
                    timeout=10.0
                )

                if response.status_code == 429:
                    self.limiter.on_rate_limit()
                    raise Exception("Rate limited")

                response.raise_for_status()
                self.limiter.on_success()
                return response.json()

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                self.limiter.on_rate_limit()
            else:
                self.limiter.on_error()
            raise
        except Exception as e:
            self.limiter.on_error()
            raise

    async def fetch_context(self, symbols: List[str]) -> Dict[str, Any]:
        """
        Fetch main context data using metaAndAssetCtxs endpoint.

        Returns funding, OI, volume, mark/oracle prices for all assets.
        """
        try:
            data = await self._request({"type": "metaAndAssetCtxs"})

            # data is [meta, assetCtxs]
            # meta['universe'] has asset definitions
            # assetCtxs is parallel array of contexts
            universe = data[0]["universe"]
            asset_ctxs = data[1]

            result = {}
            poll_ts = int(time.time() * 1000)

            for i, asset_info in enumerate(universe):
                venue_symbol = asset_info["name"]
                canonical = self.normalize_symbol(venue_symbol)

                if canonical not in symbols:
                    continue

                ctx = asset_ctxs[i]

                result[canonical] = {
                    "venue": self.venue,
                    "symbol": canonical,
                    "symbol_raw": venue_symbol,
                    "poll_ts": poll_ts,
                    "funding": {
                        "rate": float(ctx.get("funding", 0)),
                        "source": "metaAndAssetCtxs"
                    },
                    "oi": {
                        "value": float(ctx.get("openInterest", 0)),
                        "unit": "asset",  # HL reports in asset units
                        "source": "metaAndAssetCtxs"
                    },
                    "volume": {
                        "value_24h": float(ctx.get("dayNtlVlm", 0)),
                        "unit": "usd",
                        "source": "metaAndAssetCtxs"
                    },
                    "price": {
                        "mark": float(ctx.get("markPx", 0)),
                        "oracle": float(ctx.get("oraclePx", 0)),
                        "premium": float(ctx.get("premium", 0))
                    },
                    "meta": {
                        "max_leverage": asset_info.get("maxLeverage", 50),
                        "sz_decimals": asset_info.get("szDecimals", 5)
                    }
                }

            logger.debug(f"Fetched context for {len(result)} symbols from Hyperliquid")
            return result

        except Exception as e:
            logger.error(f"Error fetching Hyperliquid context: {e}")
            return {}

    async def fetch_orderbook(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Fetch L2 orderbook for a symbol.

        Returns 20 levels per side.
        """
        try:
            hl_symbol = self.denormalize_symbol(symbol)
            data = await self._request({"type": "l2Book", "coin": hl_symbol})

            poll_ts = int(time.time() * 1000)

            # data has 'levels' with [bids, asks]
            levels = data.get("levels", [[], []])
            bids = levels[0] if len(levels) > 0 else []
            asks = levels[1] if len(levels) > 1 else []

            # Parse bids and asks
            parsed_bids = []
            parsed_asks = []

            for bid in bids:
                parsed_bids.append({
                    "price": float(bid.get("px", 0)),
                    "size": float(bid.get("sz", 0)),
                    "orders": int(bid.get("n", 0))
                })

            for ask in asks:
                parsed_asks.append({
                    "price": float(ask.get("px", 0)),
                    "size": float(ask.get("sz", 0)),
                    "orders": int(ask.get("n", 0))
                })

            # Calculate spread
            best_bid = parsed_bids[0]["price"] if parsed_bids else 0
            best_ask = parsed_asks[0]["price"] if parsed_asks else 0
            mid_price = (best_bid + best_ask) / 2 if best_bid and best_ask else 0
            spread_usd = best_ask - best_bid if best_bid and best_ask else 0
            spread_bps = (spread_usd / mid_price * 10000) if mid_price else 0

            # Calculate depth within 1% and 2% of mid
            depth_1pct = {"bid": 0.0, "ask": 0.0}
            depth_2pct = {"bid": 0.0, "ask": 0.0}

            if mid_price > 0:
                threshold_1pct = mid_price * 0.01
                threshold_2pct = mid_price * 0.02

                for bid in parsed_bids:
                    diff = mid_price - bid["price"]
                    value = bid["price"] * bid["size"]
                    if diff <= threshold_1pct:
                        depth_1pct["bid"] += value
                    if diff <= threshold_2pct:
                        depth_2pct["bid"] += value

                for ask in parsed_asks:
                    diff = ask["price"] - mid_price
                    value = ask["price"] * ask["size"]
                    if diff <= threshold_1pct:
                        depth_1pct["ask"] += value
                    if diff <= threshold_2pct:
                        depth_2pct["ask"] += value

            # Calculate imbalance
            total_1pct = depth_1pct["bid"] + depth_1pct["ask"]
            imbalance_1pct = 0
            if total_1pct > 0:
                imbalance_1pct = (depth_1pct["bid"] - depth_1pct["ask"]) / total_1pct

            return {
                "venue": self.venue,
                "symbol": symbol,
                "poll_ts": poll_ts,
                "bids": parsed_bids[:10],  # Top 10 only
                "asks": parsed_asks[:10],
                "best_bid": best_bid,
                "best_ask": best_ask,
                "mid_price": mid_price,
                "spread_usd": spread_usd,
                "spread_bps": round(spread_bps, 2),
                "depth": {
                    "bid_1pct_usd": depth_1pct["bid"],
                    "ask_1pct_usd": depth_1pct["ask"],
                    "bid_2pct_usd": depth_2pct["bid"],
                    "ask_2pct_usd": depth_2pct["ask"]
                },
                "imbalance_1pct": round(imbalance_1pct, 4),
                "source": "l2Book"
            }

        except Exception as e:
            logger.error(f"Error fetching Hyperliquid orderbook for {symbol}: {e}")
            return None

    async def fetch_funding_history(
        self,
        symbol: str,
        start_time: int
    ) -> List[Dict[str, Any]]:
        """
        Fetch historical funding rates.

        Args:
            symbol: Canonical symbol
            start_time: Unix timestamp (ms)
        """
        try:
            hl_symbol = self.denormalize_symbol(symbol)
            data = await self._request({
                "type": "fundingHistory",
                "coin": hl_symbol,
                "startTime": start_time
            })

            result = []
            for entry in data:
                result.append({
                    "venue": self.venue,
                    "symbol": symbol,
                    "rate": float(entry.get("fundingRate", 0)),
                    "premium": float(entry.get("premium", 0)),
                    "ts": int(entry.get("time", 0)),
                    "source": "fundingHistory"
                })

            logger.debug(f"Fetched {len(result)} funding history entries for {symbol}")
            return result

        except Exception as e:
            logger.error(f"Error fetching Hyperliquid funding history: {e}")
            return []

    async def fetch_predicted_funding(self) -> Dict[str, Any]:
        """Fetch predicted funding rates (cross-venue)."""
        try:
            data = await self._request({"type": "predictedFundings"})
            return data
        except Exception as e:
            logger.error(f"Error fetching predicted funding: {e}")
            return {}
