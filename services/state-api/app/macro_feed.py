"""
Phase 3C: Macro Feed MVP

Simple RSS-based macro headline aggregator for trading context.
Fetches headlines from configurable financial news sources.
"""

import os
import asyncio
import logging
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import httpx

logger = logging.getLogger(__name__)

# Default RSS sources (can be overridden via env)
DEFAULT_RSS_SOURCES = [
    # These are placeholder URLs - replace with actual RSS feeds
    {"name": "Cointelegraph", "url": "https://cointelegraph.com/rss", "category": "crypto"},
    {"name": "CoinDesk", "url": "https://www.coindesk.com/arc/outboundfeeds/rss/", "category": "crypto"},
    {"name": "Bloomberg Crypto", "url": "https://feeds.bloomberg.com/crypto/news.rss", "category": "macro"},
]

# Cache settings
CACHE_TTL_SECONDS = int(os.getenv("MACRO_FEED_CACHE_TTL", "300"))  # 5 minutes
MAX_HEADLINES_PER_SOURCE = int(os.getenv("MACRO_FEED_MAX_PER_SOURCE", "10"))
MAX_TOTAL_HEADLINES = int(os.getenv("MACRO_FEED_MAX_TOTAL", "30"))


@dataclass
class MacroHeadline:
    """A single macro news headline."""
    title: str
    source: str
    category: str
    url: str
    published_at: Optional[str] = None
    summary: Optional[str] = None
    sentiment: Optional[str] = None  # "bullish", "bearish", "neutral", None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class MacroFeedService:
    """
    Simple RSS-based macro headline aggregator.

    Features:
    - Configurable RSS sources
    - In-memory caching with TTL
    - Async fetching
    - Basic parsing of RSS/Atom feeds
    """

    def __init__(self, sources: Optional[List[Dict[str, str]]] = None):
        self.sources = sources or self._load_sources_from_env()
        self.cache: List[MacroHeadline] = []
        self.cache_updated_at: float = 0
        self.fetch_lock = asyncio.Lock()
        self._client: Optional[httpx.AsyncClient] = None

    def _load_sources_from_env(self) -> List[Dict[str, str]]:
        """Load RSS sources from environment or use defaults."""
        sources_json = os.getenv("MACRO_RSS_SOURCES")
        if sources_json:
            import json
            try:
                return json.loads(sources_json)
            except json.JSONDecodeError:
                logger.warning("Failed to parse MACRO_RSS_SOURCES, using defaults")
        return DEFAULT_RSS_SOURCES

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(10.0),
                follow_redirects=True,
                headers={"User-Agent": "TradeSync-MacroFeed/1.0"}
            )
        return self._client

    async def close(self):
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def fetch_headlines(self, force_refresh: bool = False) -> List[MacroHeadline]:
        """
        Fetch headlines from all sources.

        Uses caching to avoid excessive requests.
        """
        now = time.time()

        # Check cache
        if not force_refresh and self.cache and (now - self.cache_updated_at) < CACHE_TTL_SECONDS:
            return self.cache

        # Acquire lock to prevent concurrent fetches
        async with self.fetch_lock:
            # Double-check after acquiring lock
            if not force_refresh and self.cache and (now - self.cache_updated_at) < CACHE_TTL_SECONDS:
                return self.cache

            headlines = []
            client = await self._get_client()

            # Fetch from all sources concurrently
            tasks = [
                self._fetch_source(client, source)
                for source in self.sources
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception):
                    logger.warning(f"Failed to fetch source: {result}")
                    continue
                headlines.extend(result)

            # Sort by published date (most recent first)
            headlines.sort(
                key=lambda h: h.published_at or "",
                reverse=True
            )

            # Limit total headlines
            headlines = headlines[:MAX_TOTAL_HEADLINES]

            # Update cache
            self.cache = headlines
            self.cache_updated_at = now

            return headlines

    async def _fetch_source(
        self,
        client: httpx.AsyncClient,
        source: Dict[str, str]
    ) -> List[MacroHeadline]:
        """Fetch headlines from a single RSS source."""
        headlines = []

        try:
            response = await client.get(source["url"])
            response.raise_for_status()

            # Parse RSS/Atom feed
            root = ET.fromstring(response.text)

            # Handle RSS 2.0
            items = root.findall(".//item")
            if not items:
                # Handle Atom
                items = root.findall(".//{http://www.w3.org/2005/Atom}entry")

            for item in items[:MAX_HEADLINES_PER_SOURCE]:
                headline = self._parse_item(item, source)
                if headline:
                    headlines.append(headline)

        except httpx.HTTPError as e:
            logger.warning(f"HTTP error fetching {source['name']}: {e}")
        except ET.ParseError as e:
            logger.warning(f"XML parse error for {source['name']}: {e}")
        except Exception as e:
            logger.warning(f"Error fetching {source['name']}: {e}")

        return headlines

    def _parse_item(
        self,
        item: ET.Element,
        source: Dict[str, str]
    ) -> Optional[MacroHeadline]:
        """Parse an RSS item or Atom entry into a MacroHeadline."""
        try:
            # Try RSS 2.0 format first
            title = item.findtext("title")
            link = item.findtext("link")
            pub_date = item.findtext("pubDate")
            description = item.findtext("description")

            # Try Atom format if RSS didn't work
            if not title:
                title = item.findtext("{http://www.w3.org/2005/Atom}title")
            if not link:
                link_elem = item.find("{http://www.w3.org/2005/Atom}link")
                if link_elem is not None:
                    link = link_elem.get("href")
            if not pub_date:
                pub_date = item.findtext("{http://www.w3.org/2005/Atom}published")
                if not pub_date:
                    pub_date = item.findtext("{http://www.w3.org/2005/Atom}updated")
            if not description:
                description = item.findtext("{http://www.w3.org/2005/Atom}summary")

            if not title or not link:
                return None

            # Basic sentiment detection (very simple MVP)
            sentiment = self._detect_sentiment(title, description)

            return MacroHeadline(
                title=title.strip(),
                source=source["name"],
                category=source.get("category", "general"),
                url=link.strip(),
                published_at=pub_date,
                summary=description[:200] if description else None,
                sentiment=sentiment
            )

        except Exception as e:
            logger.debug(f"Failed to parse item: {e}")
            return None

    def _detect_sentiment(
        self,
        title: str,
        description: Optional[str] = None
    ) -> Optional[str]:
        """
        Very basic keyword-based sentiment detection.

        This is a simple MVP - could be enhanced with ML models later.
        """
        text = (title + " " + (description or "")).lower()

        bullish_keywords = [
            "surge", "rally", "bullish", "soar", "jump", "gain",
            "breakout", "all-time high", "ath", "pump", "moon",
            "adoption", "institutional", "approval", "etf approved"
        ]

        bearish_keywords = [
            "crash", "plunge", "bearish", "drop", "fall", "dump",
            "sell-off", "selloff", "collapse", "fear", "panic",
            "hack", "exploit", "scam", "fraud", "ban", "regulation"
        ]

        bullish_count = sum(1 for kw in bullish_keywords if kw in text)
        bearish_count = sum(1 for kw in bearish_keywords if kw in text)

        if bullish_count > bearish_count and bullish_count >= 1:
            return "bullish"
        elif bearish_count > bullish_count and bearish_count >= 1:
            return "bearish"
        else:
            return "neutral"

    def get_status(self) -> Dict[str, Any]:
        """Get service status."""
        return {
            "sources_configured": len(self.sources),
            "headlines_cached": len(self.cache),
            "cache_age_seconds": time.time() - self.cache_updated_at if self.cache_updated_at else None,
            "cache_ttl_seconds": CACHE_TTL_SECONDS,
            "sources": [s["name"] for s in self.sources]
        }


# Global instance
macro_feed = MacroFeedService()
