from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from datetime import datetime

class NormalizedEvent(BaseModel):
    id: str
    ts: datetime
    source: str
    kind: str
    symbol: str
    timeframe: str
    payload: Dict[str, Any]
    provenance: Dict[str, Any]
    hash: str
