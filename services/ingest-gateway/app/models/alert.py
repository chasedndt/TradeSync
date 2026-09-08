from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class TradingViewAlert(BaseModel):
    symbol: str = Field(..., description="Trading pair symbol, e.g. BTCUSDT")
    timeframe: str = Field(..., description="Timeframe of the alert, e.g. 15m, 1h")
    bias: Optional[str] = Field(None, description="Directional bias: LONG, SHORT, or NEUTRAL")
    confidence: Optional[float] = Field(None, ge=0, le=100, description="Confidence score 0-100")
    price: Optional[float] = Field(None, description="Price at the time of alert")
    source: str = Field("tradingview", description="Source of the alert")
    passphrase: Optional[str] = Field(None, description="Security passphrase if used")

    model_config = ConfigDict(extra="ignore")
