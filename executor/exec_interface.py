from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from pydantic import BaseModel

class OrderRequest(BaseModel):
    symbol: str
    size: float
    action: str  # "BUY" or "SELL" / "LONG" or "SHORT"
    order_type: str = "MARKET"
    # price: Optional[float] = None

class ExecutionResult(BaseModel):
    execution_id: str
    status: str
    venue_order_id: Optional[str] = None
    details: Dict[str, Any] = {}

class BaseExecutor(ABC):
    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run

    @abstractmethod
    async def execute_order(self, order: OrderRequest) -> ExecutionResult:
        """
        Execute an order on the venue.
        Should respect self.dry_run.
        """
        pass
