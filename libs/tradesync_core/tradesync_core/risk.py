"""
Risk guardian: comprehensive trade validation.
Extracted verbatim from services/state-api/app/risk.py (Phase 3C).
"""

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
    # Phase 3C: New microstructure-based block codes
    SPREAD_TOO_WIDE = "SPREAD_TOO_WIDE"
    SLIPPAGE_TOO_HIGH = "SLIPPAGE_TOO_HIGH"
    DEPTH_TOO_THIN = "DEPTH_TOO_THIN"
    LIQUIDITY_TOO_LOW = "LIQUIDITY_TOO_LOW"
    MARGIN_STRESS = "MARGIN_STRESS"
    EXPOSURE_TOO_HIGH = "EXPOSURE_TOO_HIGH"


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

        # Phase 3C: Microstructure thresholds
        self.max_spread_bps = float(os.getenv("MAX_SPREAD_BPS", "50.0"))
        self.min_depth_25bp_usd = float(os.getenv("MIN_DEPTH_25BP_USD", "100000"))
        self.max_impact_bps_5k = float(os.getenv("MAX_IMPACT_BPS_5K", "25.0"))
        self.min_liquidity_score = float(os.getenv("MIN_LIQUIDITY_SCORE", "0.3"))
        self.margin_stress_threshold = float(os.getenv("MARGIN_STRESS_THRESHOLD", "0.8"))
        self.max_exposure_per_symbol = float(os.getenv("MAX_EXPOSURE_PER_SYMBOL_USD", "25000"))

    def check(self,
              symbol: str,
              size_usd: float,
              opportunity: Dict[str, Any],
              latest_signal: Optional[Dict[str, Any]] = None,
              account_equity: float = 10000.0,
              open_positions_count: int = 0,
              recent_decisions_count: int = 0,
              phase: str = "preview",
              # Phase 3C: New parameters for microstructure checks
              microstructure: Optional[Dict[str, Any]] = None,
              margin_utilization: float = 0.0,
              symbol_exposure_usd: float = 0.0
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

        # Phase 3C: 5b. Microstructure Checks
        if microstructure:
            # Spread check
            spread_bps = microstructure.get("spread_bps", 0)
            if spread_bps > self.max_spread_bps:
                return RiskVerdict(
                    allowed=False,
                    reason_code=ReasonCode.SPREAD_TOO_WIDE,
                    reason=f"Spread {spread_bps:.1f} bps exceeds maximum {self.max_spread_bps:.1f} bps",
                    suggested_adjustment={"action": "WAIT", "condition": f"spread < {self.max_spread_bps} bps"}
                )

            # Depth check
            depth_25bp = microstructure.get("depth_usd", {}).get("25bp", 0)
            if depth_25bp < self.min_depth_25bp_usd:
                return RiskVerdict(
                    allowed=False,
                    reason_code=ReasonCode.DEPTH_TOO_THIN,
                    reason=f"Depth at 25bp (${depth_25bp:,.0f}) below minimum ${self.min_depth_25bp_usd:,.0f}",
                    suggested_adjustment={"action": "RESIZE", "note": "Reduce size relative to available depth"}
                )

            # Slippage/Impact check (for order size)
            impact_5k = microstructure.get("impact_est_bps", {}).get("5000", 0)
            if size_usd >= 5000 and impact_5k > self.max_impact_bps_5k:
                return RiskVerdict(
                    allowed=False,
                    reason_code=ReasonCode.SLIPPAGE_TOO_HIGH,
                    reason=f"Estimated slippage {impact_5k:.1f} bps exceeds maximum {self.max_impact_bps_5k:.1f} bps for ${size_usd:,.0f} order",
                    suggested_adjustment={"action": "RESIZE", "value": 2500, "note": "Reduce size to limit slippage"}
                )

            # Liquidity score check
            liquidity_score = microstructure.get("liquidity_score", 1.0)
            if liquidity_score < self.min_liquidity_score:
                return RiskVerdict(
                    allowed=False,
                    reason_code=ReasonCode.LIQUIDITY_TOO_LOW,
                    reason=f"Liquidity score {liquidity_score:.2f} below minimum {self.min_liquidity_score:.2f}",
                    suggested_adjustment={"action": "WAIT", "condition": f"liquidity_score >= {self.min_liquidity_score}"}
                )

        # Phase 3C: 5c. Margin Stress Check
        if margin_utilization > self.margin_stress_threshold:
            return RiskVerdict(
                allowed=False,
                reason_code=ReasonCode.MARGIN_STRESS,
                reason=f"Margin utilization {margin_utilization:.0%} exceeds stress threshold {self.margin_stress_threshold:.0%}",
                suggested_adjustment={"action": "RESIZE", "note": "Reduce size to maintain margin buffer"}
            )

        # Phase 3C: 5d. Symbol Exposure Check
        if symbol_exposure_usd + size_usd > self.max_exposure_per_symbol:
            return RiskVerdict(
                allowed=False,
                reason_code=ReasonCode.EXPOSURE_TOO_HIGH,
                reason=f"Adding ${size_usd:,.0f} would exceed per-symbol exposure limit (${self.max_exposure_per_symbol:,.0f})",
                suggested_adjustment={
                    "action": "RESIZE",
                    "value": max(0, self.max_exposure_per_symbol - symbol_exposure_usd),
                    "note": "Reduce size to stay within exposure limits"
                }
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
