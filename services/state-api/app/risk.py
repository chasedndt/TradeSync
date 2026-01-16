import os
from enum import Enum
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from pydantic import BaseModel

class ReasonCode(str, Enum):
    OK = "OK"
    EXEC_DISABLED = "EXEC_DISABLED"
    DNT = "DNT"
    STALE_DATA = "STALE_DATA"
    EXPIRED = "EXPIRED"
    DUPLICATE = "DUPLICATE"
    COOLDOWN = "COOLDOWN"
    LIMIT_DAILY = "LIMIT_DAILY"
    LIMIT_POSITIONS = "LIMIT_POSITIONS"
    MIN_QUALITY = "MIN_QUALITY"
    MIN_SIZE = "MIN_SIZE"
    MAX_LEVERAGE = "MAX_LEVERAGE"

class RiskVerdict(BaseModel):
    allowed: bool
    reason_code: ReasonCode
    reason: str
    suggested_adjustment: Optional[Dict[str, Any]] = None

class RiskGuardian:
    def __init__(self):
        self.execution_enabled = os.getenv("EXECUTION_ENABLED", "false").lower() == "true"
        self.max_leverage = float(os.getenv("MAX_LEVERAGE", "5.0"))
        self.blacklist = os.getenv("DNT_LIST", "LUNA,FTX,FTT").split(",")
        self.max_event_age = int(os.getenv("MAX_EVENT_AGE_SECONDS", "300"))
        self.max_signal_age = int(os.getenv("MAX_SIGNAL_AGE_SECONDS", "300"))
        self.min_quality = float(os.getenv("MIN_QUALITY", "50.0"))

    def check(self, 
              symbol: str, 
              size_usd: float, 
              opportunity: Dict[str, Any],
              latest_signal: Optional[Dict[str, Any]] = None,
              account_equity: float = 10000.0,
              open_positions_count: int = 0,
              recent_decisions_count: int = 0,
              phase: str = "preview"
              ) -> RiskVerdict:
        """
        Validates a proposed trade against comprehensive hardening rules.
        """
        # 0. Global Killswitch
        if not self.execution_enabled:
            return RiskVerdict(
                allowed=False, 
                reason_code=ReasonCode.EXEC_DISABLED,
                reason="Global execution gate is DISABLED"
            )

        # 1. DNT List
        if any(b in symbol for b in self.blacklist if b):
            return RiskVerdict(
                allowed=False, 
                reason_code=ReasonCode.DNT,
                reason=f"Symbol {symbol} is on the Do Not Trade (DNT) list"
            )

        # 2. Duplicate / Status Check
        status = opportunity.get("status")
        if phase == "preview" and status != "new":
            return RiskVerdict(
                allowed=False,
                reason_code=ReasonCode.DUPLICATE,
                reason=f"Opportunity is already in status: {status}"
            )
        if phase == "execute" and status not in ["new", "previewed"]:
             return RiskVerdict(
                allowed=False,
                reason_code=ReasonCode.DUPLICATE,
                reason=f"Execution rejected: Opportunity status is {status}"
            )
        
        # 3. Expiry Check
        expires_at = opportunity.get("expires_at")
        if expires_at:
            if isinstance(expires_at, str):
                expires_at = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
            if datetime.now(timezone.utc) > expires_at:
                return RiskVerdict(
                    allowed=False,
                    reason_code=ReasonCode.EXPIRED,
                    reason="Opportunity has expired"
                )

        if latest_signal:
            signal_ts = latest_signal.get("created_at")
            if signal_ts:
                if isinstance(signal_ts, str):
                    signal_ts = datetime.fromisoformat(signal_ts.replace('Z', '+00:00'))
                
                # Ensure aware
                if signal_ts.tzinfo is None:
                    signal_ts = signal_ts.replace(tzinfo=timezone.utc)
                    
                age = (datetime.now(timezone.utc) - signal_ts).total_seconds()
                if age > self.max_signal_age:
                    return RiskVerdict(
                        allowed=False,
                        reason_code=ReasonCode.STALE_DATA,
                        reason=f"Signal is too stale ({age:.0f}s > {self.max_signal_age}s)"
                    )

        # 5. Quality Gate
        quality = opportunity.get("quality", 0)
        if quality < self.min_quality:
            return RiskVerdict(
                allowed=False,
                reason_code=ReasonCode.MIN_QUALITY,
                reason=f"Quality {quality:.1f} below minimum {self.min_quality}"
            )

        # 6. Exposure / Limit Checks
        if open_positions_count >= int(os.getenv("MAX_OPEN_POSITIONS", "10")):
             return RiskVerdict(
                allowed=False,
                reason_code=ReasonCode.LIMIT_POSITIONS,
                reason="Max open positions reached"
            )

        # 7. Cooldown / Duplicate Decision Check
        if recent_decisions_count > 0:
            return RiskVerdict(
                allowed=False,
                reason_code=ReasonCode.COOLDOWN,
                reason="Rate limit: Duplicate decision or cooldown active for this opportunity"
            )

        # 8. Size / Leverage Checks
        if size_usd < float(os.getenv("MIN_SIZE_USD", "10.0")):
            return RiskVerdict(
                allowed=False, 
                reason_code=ReasonCode.MIN_SIZE,
                reason="Size too small (< $10)"
            )

        implied_leverage = size_usd / account_equity
        if implied_leverage > self.max_leverage:
             return RiskVerdict(
                 allowed=False, 
                 reason_code=ReasonCode.MAX_LEVERAGE,
                 reason=f"Leverage {implied_leverage:.2f}x exceeds limit {self.max_leverage}x",
                 suggested_adjustment={"action": "RESIZE", "value": account_equity * self.max_leverage}
             )
             
        return RiskVerdict(
            allowed=True, 
            reason_code=ReasonCode.OK,
            reason="All risk checks passed"
        )
