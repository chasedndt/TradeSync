from pydantic import BaseModel, Field
from typing import Dict, Any, Optional

class MarketSnapshot(BaseModel):
    source: str = Field(..., description="Source exchange, e.g. hyperliquid, drift")
    symbol: str = Field(..., description="Market symbol, e.g. BTC-USD")
    mark: float = Field(..., description="Mark price")
    funding: float = Field(..., description="Funding rate")
    oi: float = Field(..., description="Open interest")
    volume: float = Field(..., description="24h Volume")
    raw: Dict[str, Any] = Field(..., description="Raw JSON payload from source")
