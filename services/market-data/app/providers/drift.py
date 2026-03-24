"""
Drift Protocol market data provider.

API Documentation: https://drift-labs.github.io/v2-teacher/
Data API: https://data.api.drift.trade
"""

import httpx
import logging
import time
from typing import Dict, List, Any, Optional

from .base import BaseProvider
from ..rate_limiter import get_limiter

logger = logging.getLogger(__name__)

DRIFT_API_URL = "https://data.api.drift.trade"
DRIFT_DLOB_URL = "https://dlob.drift.trade"


class DriftProvider(BaseProvider):
    """Drift Protocol market data provider."""

    def __init__(self):
        super().__init__("drift")
        self.api_url = DRIFT_API_URL
        self.dlob_url = DRIFT_DLOB_URL
        self.limiter = get_limiter("drift")

        # Drift already uses canonical format
        self._symbol_map = {
            "BTC-PERP": "BTC-PERP",
            "ETH-PERP": "ETH-PERP",
            "SOL-PERP": "SOL-PERP",
        }
        # Market index mapping
        self._market_index = {
            "BTC-PERP": 0,
            "ETH-PERP": 1,
            "SOL-PERP": 2,
        }

    def normalize_symbol(self, venue_symbol: str) -> str:
        """Drift uses canonical format already."""
        return venue_symbol.upper()

    def denormalize_symbol(self, canonical_symbol: str) -> str:
        """No transformation needed."""
        return canonical_symbol

    def get_market_index(self, symbol: str) -> int:
        """Get market index for symbol."""
        return self._market_index.get(symbol, 0)

    async def _request(self, endpoint: str, params: Dict = None) -> Any:
        """Make rate-limited GET request to Drift API."""
        await self.limiter.acquire()

        url = f"{self.api_url}{endpoint}"

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url,
                    params=params,
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
        Fetch main context data using /contracts endpoint.

        Returns funding, OI, volume, prices for all perp contracts.
        """
        try:
            data = await self._request("/contracts")

            result = {}
            poll_ts = int(time.time() * 1000)

            # data is a list of contracts
            contracts = data if isinstance(data, list) else data.get("contracts", [])

            for contract in contracts:
                ticker = contract.get("ticker_id", "")

                if ticker not in symbols:
                    continue

                # Drift reports OI in USD
                oi_usd = float(contract.get("open_interest", 0))
                last_price = float(contract.get("last_price", 0))

                result[ticker] = {
                    "venue": self.venue,
                    "symbol": ticker,
                    "symbol_raw": ticker,
                    "poll_ts": poll_ts,
                    "funding": {
                        "rate": float(contract.get("funding_rate", 0)),
                        "source": "contracts"
                    },
                    "oi": {
                        "value": oi_usd,
                        "unit": "usd",  # Drift reports in USD
                        "source": "contracts"
                    },
                    "volume": {
                        "value_24h": float(contract.get("24h_volume", 0)),
                        "unit": "usd",
                        "source": "contracts"
                    },
                    "price": {
                        "mark": float(contract.get("mark_price", last_price)),
                        "index": float(contract.get("index_price", 0)),
                        "last": last_price
                    },
                    "meta": {
                        "max_leverage": int(contract.get("max_leverage", 20)),
                        "market_index": contract.get("market_index", 0)
                    }
                }

            logger.debug(f"Fetched context for {len(result)} symbols from Drift")
            return result

        except Exception as e:
            logger.error(f"Error fetching Drift context: {e}")
            return {}

    async def fetch_orderbook(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Fetch L2 orderbook from DLOB server.
        """
        try:
            market_index = self.get_market_index(symbol)

            # Use DLOB endpoint
            url = f"{self.dlob_url}/l2"
            params = {
                "marketIndex": market_index,
                "marketType": "perp"
            }

            await self.limiter.acquire()

            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, timeout=10.0)

                if response.status_code == 429:
                    self.limiter.on_rate_limit()
                    raise Exception("Rate limited")

                response.raise_for_status()
                self.limiter.on_success()
                data = response.json()

            poll_ts = int(time.time() * 1000)

            # Parse bids and asks
            bids = data.get("bids", [])
            asks = data.get("asks", [])

            parsed_bids = []
            parsed_asks = []

            for bid in bids[:20]:
                parsed_bids.append({
                    "price": float(bid.get("price", 0)),
                    "size": float(bid.get("size", 0)),
                    "orders": 1  # DLOB doesn't provide order count
                })

            for ask in asks[:20]:
                parsed_asks.append({
                    "price": float(ask.get("price", 0)),
                    "size": float(ask.get("size", 0)),
                    "orders": 1
                })

            # Sort: bids descending, asks ascending
            parsed_bids.sort(key=lambda x: x["price"], reverse=True)
            parsed_asks.sort(key=lambda x: x["price"])

            # Calculate spread
            best_bid = parsed_bids[0]["price"] if parsed_bids else 0
            best_ask = parsed_asks[0]["price"] if parsed_asks else 0
            mid_price = (best_bid + best_ask) / 2 if best_bid and best_ask else 0
            spread_usd = best_ask - best_bid if best_bid and best_ask else 0
            spread_bps = (spread_usd / mid_price * 10000) if mid_price else 0

            # Calculate depth
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
                "bids": parsed_bids[:10],
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
                "source": "dlob/l2"
            }

        except Exception as e:
            logger.error(f"Error fetching Drift orderbook for {symbol}: {e}")
            return None

    async def fetch_funding_history(
        self,
        symbol: str,
        start_time: int
    ) -> List[Dict[str, Any]]:
        """
        Fetch historical funding rates.
        """
        try:
            market_index = self.get_market_index(symbol)
            data = await self._request("/fundingRates", {
                "marketIndex": market_index
            })

            result = []
            rates = data if isinstance(data, list) else data.get("rates", [])

            for entry in rates:
                ts = int(entry.get("timestamp", 0))
                if ts >= start_time:
                    result.append({
                        "venue": self.venue,
                        "symbol": symbol,
                        "rate": float(entry.get("funding_rate", 0)),
                        "ts": ts,
                        "source": "fundingRates"
                    })

            logger.debug(f"Fetched {len(result)} funding history entries for {symbol}")
            return result

        except Exception as e:
            logger.error(f"Error fetching Drift funding history: {e}")
            return []
