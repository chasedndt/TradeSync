"""
MarketSnapshot models for Phase 3B - Market Data Expansion.

These models implement the contract defined in docs/contracts/MARKET_CONTRACT.md
"""

from enum import Enum
from typing import Optional, Dict, List, Any
from pydantic import BaseModel, Field
from datetime import datetime


# === Enums ===

class MetricStatus(str, Enum):
    REAL = "REAL"
    PROXY = "PROXY"
    UNAVAILABLE = "UNAVAILABLE"
    STALE = "STALE"


class FundingRegime(str, Enum):
    EXTREME_POSITIVE = "extreme_positive"
    ELEVATED_POSITIVE = "elevated_positive"
    NEUTRAL = "neutral"
    ELEVATED_NEGATIVE = "elevated_negative"
    EXTREME_NEGATIVE = "extreme_negative"


class OIRegime(str, Enum):
    BUILD = "build"
    UNWIND = "unwind"
    FLAT = "flat"


class VolumeRegime(str, Enum):
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class TrendRegime(str, Enum):
    STRONG_TREND = "strong_trend"
    WEAK_TREND = "weak_trend"
    RANGE = "range"


class MarketCondition(str, Enum):
    TRENDING_HEALTHY = "trending_healthy"
    SQUEEZE_RISK = "squeeze_risk"
    CAPITULATION = "capitulation"
    CHOPPY = "choppy"
    UNKNOWN = "unknown"


# === Component Models ===

class MetricAvailability(BaseModel):
    metric: str
    status: MetricStatus
    source: Optional[str] = None
    last_updated: Optional[int] = None
    note: Optional[str] = None


class FundingHorizons(BaseModel):
    now: float = 0.0
    h8: float = 0.0   # 8h average
    h24: float = 0.0  # 24h average
    d3: float = 0.0   # 3d average
    d7: float = 0.0   # 7d average


class FundingSource(BaseModel):
    provider: str
    endpoint: str
    raw_rate: float


class FundingData(BaseModel):
    horizons: FundingHorizons
    annualized_24h: float = 0.0
    regime: FundingRegime = FundingRegime.NEUTRAL
    source: FundingSource


class HorizonValue(BaseModel):
    value: float = 0.0
    delta_pct: float = 0.0
    delta_usd: float = 0.0


class OpenInterestData(BaseModel):
    horizons: Dict[str, HorizonValue] = Field(default_factory=dict)
    current_usd: float = 0.0
    regime: OIRegime = OIRegime.FLAT


class LiquidationWindow(BaseModel):
    longs_usd: float = 0.0
    shorts_usd: float = 0.0
    total_usd: float = 0.0
    dominant_side: str = "balanced"


class LiquidationData(BaseModel):
    horizons: Dict[str, LiquidationWindow] = Field(default_factory=dict)
    source_note: Optional[str] = None
    method: str = "real"


class OrderbookDepth(BaseModel):
    bid_1pct_usd: float = 0.0
    ask_1pct_usd: float = 0.0
    bid_2pct_usd: float = 0.0
    ask_2pct_usd: float = 0.0


# === Phase 3C: Microstructure Models ===

class BookHeatmapLevel(BaseModel):
    """Single level in the book heatmap visualization."""
    price: float
    side: str  # "bid" or "ask"
    size_usd: float


class MicrostructureData(BaseModel):
    """
    Derived microstructure metrics for liquidity analysis (Phase 3C).

    These fields are computed from raw orderbook data to enable:
    - Liquidity heatmap visualization
    - Slippage/impact estimation for position sizing
    - Execution risk assessment
    """
    spread_bps: float = 0.0
    mid_price: float = 0.0

    # Depth in USD at various BPS thresholds from mid
    depth_usd: Dict[str, float] = Field(default_factory=dict)  # {"10bp": x, "25bp": y, "50bp": z}

    # Estimated price impact in BPS for various order sizes
    impact_est_bps: Dict[str, float] = Field(default_factory=dict)  # {"1000": x, "5000": y, "10000": z}

    # Composite liquidity score 0-1 (higher = more liquid)
    liquidity_score: float = 0.0

    # Compact heatmap for visualization (top N levels per side)
    book_heatmap: List[BookHeatmapLevel] = Field(default_factory=list)


class OrderbookData(BaseModel):
    spread_bps: float = 0.0
    spread_usd: float = 0.0
    depth: OrderbookDepth = Field(default_factory=OrderbookDepth)
    imbalance_1pct: float = 0.0
    best_bid: float = 0.0
    best_ask: float = 0.0
    mid_price: float = 0.0
    book_age_ms: int = 0


class VolumeData(BaseModel):
    horizons: Dict[str, float] = Field(default_factory=dict)
    cvd: Optional[Dict[str, float]] = None
    cvd_method: Optional[str] = None
    avg_7d_daily: float = 0.0
    regime: VolumeRegime = VolumeRegime.NORMAL


class RegimeSummary(BaseModel):
    funding: FundingRegime = FundingRegime.NEUTRAL
    oi: OIRegime = OIRegime.FLAT
    volume: VolumeRegime = VolumeRegime.NORMAL
    trend: TrendRegime = TrendRegime.RANGE
    market_condition: MarketCondition = MarketCondition.UNKNOWN
    confidence: str = "low"
    confidence_note: Optional[str] = None


class SourceMetadata(BaseModel):
    provider: str
    endpoint: str
    fetched_at: int
    metrics_provided: List[str]


# === Main Snapshot Model ===

class MarketSnapshot(BaseModel):
    """
    The canonical market snapshot for a venue/symbol pair.
    Implements the contract from docs/contracts/MARKET_CONTRACT.md
    """
    venue: str
    symbol: str  # Canonical format: "BTC-PERP"
    ts: int  # Unix timestamp (ms)
    data_age_ms: int = 0

    available_metrics: List[MetricAvailability] = Field(default_factory=list)

    funding: Optional[FundingData] = None
    oi: Optional[OpenInterestData] = None
    liquidations: Optional[LiquidationData] = None
    volume: Optional[VolumeData] = None
    orderbook: Optional[OrderbookData] = None

    # Phase 3C: Derived microstructure data
    microstructure: Optional[MicrostructureData] = None

    regimes: RegimeSummary = Field(default_factory=RegimeSummary)
    sources: List[SourceMetadata] = Field(default_factory=list)


# === Raw Event Models (for Redis streams) ===

class RawMarketEvent(BaseModel):
    """Raw event from provider, before normalization."""
    id: str
    venue: str
    metric_type: str  # "funding", "oi", "orderbook", "volume"
    symbol_raw: str  # Venue-specific symbol
    payload: Dict[str, Any]
    poll_ts: int  # When we polled


class NormalizedMarketEvent(BaseModel):
    """Normalized event, ready for snapshotting."""
    id: str
    venue: str
    symbol: str  # Canonical symbol
    metric_type: str
    ts: int
    data_age_ms: int
    status: MetricStatus
    source: SourceMetadata
    value: Dict[str, Any]


class MarketAlert(BaseModel):
    """Alert for regime changes or extreme values."""
    id: str
    venue: str
    symbol: str
    ts: int
    alert_type: str  # "regime_change", "extreme_value", "stale_data"
    metric: str
    previous_value: Optional[str] = None
    new_value: str
    context: Dict[str, Any] = Field(default_factory=dict)
