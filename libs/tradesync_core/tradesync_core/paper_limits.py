"""Managed-paper risk limits: the entry verdict, standing breaches and limit utilisation.

Nothing here raises a limit. Limits change only through the operator's audited
route (``paper_risk_limits`` in ``ops/migrations/031``). An evaluation can refuse
an entry, or report a standing daily-loss or drawdown breach that switches the
persistent entry pause on; it can never loosen a limit.

Exposure is gross: the absolute notional of every open position at its mark,
long and short alike, as a fraction of equity.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from tradesync_core.paper_account import AccountSnapshot
from tradesync_core.paper_correlation import MAX_AGE_S, BucketView

LIMIT_KEYS = (
    "daily_loss_limit_usdc",
    "max_drawdown_fraction",
    "max_gross_exposure_fraction",
    "max_symbol_exposure_fraction",
    "max_bucket_exposure_fraction",
    "correlation_threshold",
    "max_concurrent_positions",
    "max_entry_quote_age_s",
    "max_mark_age_s",
)
FUTURE_TOLERANCE_S = 2.0


class Code:
    """Reason codes carried by an entry refusal. Stable strings; the Cockpit and tests read them."""

    KILL_SWITCH_ACTIVE = "KILL_SWITCH_ACTIVE"
    RECONCILIATION_PENDING = "RECONCILIATION_PENDING"
    RECONCILIATION_MISMATCH = "RECONCILIATION_MISMATCH"
    ACCOUNT_UNAVAILABLE = "ACCOUNT_UNAVAILABLE"
    LIMITS_UNAVAILABLE = "LIMITS_UNAVAILABLE"
    NON_POSITIVE_EQUITY = "NON_POSITIVE_EQUITY"
    DAILY_LOSS_LIMIT = "DAILY_LOSS_LIMIT"
    DAILY_LOSS_BUDGET = "DAILY_LOSS_BUDGET"
    DRAWDOWN_LIMIT = "DRAWDOWN_LIMIT"
    DRAWDOWN_BUDGET = "DRAWDOWN_BUDGET"
    MAX_POSITIONS_LIMIT = "MAX_POSITIONS_LIMIT"
    STALE_ENTRY_QUOTE = "STALE_ENTRY_QUOTE"
    STALE_POSITION_MARK = "STALE_POSITION_MARK"
    GROSS_EXPOSURE_LIMIT = "GROSS_EXPOSURE_LIMIT"
    SYMBOL_EXPOSURE_LIMIT = "SYMBOL_EXPOSURE_LIMIT"
    CORRELATED_EXPOSURE_LIMIT = "CORRELATED_EXPOSURE_LIMIT"
    CORRELATION_UNAVAILABLE = "CORRELATION_UNAVAILABLE"


# A standing breach of these switches the persistent entry pause on.
PAUSING = frozenset({Code.DAILY_LOSS_LIMIT, Code.DRAWDOWN_LIMIT})


@dataclass(frozen=True)
class Refusal:
    code: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


@dataclass(frozen=True)
class Entry:
    symbol: str
    notional_usdc: float
    planned_risk_usdc: float
    quote_time: float


def check_limits(values: Mapping[str, Any]) -> dict[str, Any]:
    """Limits as numbers, with the ordering the database also enforces."""
    missing = [key for key in LIMIT_KEYS if values.get(key) is None]
    if missing:
        raise ValueError("Paper limits missing: " + ", ".join(missing))
    limits: dict[str, Any] = {key: float(values[key]) for key in LIMIT_KEYS}
    limits["max_concurrent_positions"] = int(values["max_concurrent_positions"])
    if not limits["max_symbol_exposure_fraction"] <= limits["max_bucket_exposure_fraction"] <= limits["max_gross_exposure_fraction"]:
        raise ValueError("Per-symbol exposure must not exceed the correlated bucket limit, nor the bucket limit gross exposure")
    return limits


def usd(value: float) -> str:
    return f"{value:,.2f} USDC"


def pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def standing_breaches(account: AccountSnapshot, limits: Mapping[str, Any]) -> list[Refusal]:
    found = []
    if account.day_pnl_usdc <= -limits["daily_loss_limit_usdc"]:
        found.append(Refusal(Code.DAILY_LOSS_LIMIT, f"Day P&L {usd(account.day_pnl_usdc)} reached the daily loss limit of {usd(limits['daily_loss_limit_usdc'])}"))
    if account.drawdown_fraction >= limits["max_drawdown_fraction"]:
        found.append(Refusal(Code.DRAWDOWN_LIMIT, f"Drawdown {pct(account.drawdown_fraction)} from peak equity {usd(account.peak_equity_usdc)} reached the {pct(limits['max_drawdown_fraction'])} limit"))
    return found


def stale_marks(account: AccountSnapshot, limits: Mapping[str, Any], now_s: float) -> list[Refusal]:
    stale = [m for m in account.marks if now_s - m.marked_at > limits["max_mark_age_s"]]
    if not stale:
        return []
    names = ", ".join(sorted({m.symbol for m in stale}))
    oldest = max(now_s - m.marked_at for m in stale)
    return [Refusal(Code.STALE_POSITION_MARK, f"Open paper position marks are stale ({names}; oldest {oldest:.0f}s, limit {limits['max_mark_age_s']:.0f}s)")]


def bucket_symbols(symbol: str, account: AccountSnapshot, buckets: BucketView) -> set[str]:
    """The symbol's measured bucket, plus open symbols with no measurement, counted in conservatively."""
    group = buckets.members(symbol) or (symbol,)
    return set(group) | {s for s in account.exposure_by_symbol if s not in buckets.grouped()}


def evaluate_entry(entry: Entry, account: AccountSnapshot, limits: Mapping[str, Any], *,
                   buckets: BucketView | None, now_s: float) -> list[Refusal]:
    """Every limit a new paper entry would breach; empty means the limits admit it."""
    equity = account.equity_usdc
    if equity <= 0:
        return [Refusal(Code.NON_POSITIVE_EQUITY, f"Equity {usd(equity)} is not positive")]
    refusals = standing_breaches(account, limits)
    codes = {r.code for r in refusals}
    if Code.DAILY_LOSS_LIMIT not in codes and account.day_pnl_usdc - entry.planned_risk_usdc <= -limits["daily_loss_limit_usdc"]:
        refusals.append(Refusal(Code.DAILY_LOSS_BUDGET, f"Planned risk {usd(entry.planned_risk_usdc)} would take day P&L {usd(account.day_pnl_usdc)} past the {usd(limits['daily_loss_limit_usdc'])} daily loss limit"))
    projected = (account.peak_equity_usdc - (equity - entry.planned_risk_usdc)) / account.peak_equity_usdc
    if Code.DRAWDOWN_LIMIT not in codes and projected >= limits["max_drawdown_fraction"]:
        refusals.append(Refusal(Code.DRAWDOWN_BUDGET, f"Planned risk {usd(entry.planned_risk_usdc)} would take drawdown to {pct(projected)}, past the {pct(limits['max_drawdown_fraction'])} limit"))
    if len(account.marks) + 1 > limits["max_concurrent_positions"]:
        refusals.append(Refusal(Code.MAX_POSITIONS_LIMIT, f"{len(account.marks)} open paper positions; the limit is {limits['max_concurrent_positions']}"))
    age = now_s - entry.quote_time
    if age > limits["max_entry_quote_age_s"] or age < -FUTURE_TOLERANCE_S:
        refusals.append(Refusal(Code.STALE_ENTRY_QUOTE, f"Entry quote is {age:.1f}s old; the limit is {limits['max_entry_quote_age_s']:.0f}s"))
    refusals += stale_marks(account, limits, now_s)
    gross = (account.gross_exposure_usdc + entry.notional_usdc) / equity
    if gross > limits["max_gross_exposure_fraction"]:
        refusals.append(Refusal(Code.GROSS_EXPOSURE_LIMIT, f"Gross exposure would be {pct(gross)} of equity; the limit is {pct(limits['max_gross_exposure_fraction'])}"))
    single = (account.exposure_by_symbol.get(entry.symbol, 0.0) + entry.notional_usdc) / equity
    if single > limits["max_symbol_exposure_fraction"]:
        refusals.append(Refusal(Code.SYMBOL_EXPOSURE_LIMIT, f"{entry.symbol} exposure would be {pct(single)} of equity; the limit is {pct(limits['max_symbol_exposure_fraction'])}"))
    if buckets is None or now_s - buckets.measured_at > MAX_AGE_S or entry.symbol in buckets.unmeasured or buckets.members(entry.symbol) is None:
        refusals.append(Refusal(Code.CORRELATION_UNAVAILABLE, f"No current correlation measurement covers {entry.symbol}; correlated exposure cannot be bounded"))
    else:
        members = bucket_symbols(entry.symbol, account, buckets)
        combined = (sum(account.exposure_by_symbol.get(s, 0.0) for s in members) + entry.notional_usdc) / equity
        if combined > limits["max_bucket_exposure_fraction"]:
            refusals.append(Refusal(Code.CORRELATED_EXPOSURE_LIMIT, f"Correlated exposure ({', '.join(sorted(members))}) would be {pct(combined)} of equity; the limit is {pct(limits['max_bucket_exposure_fraction'])}"))
    return refusals


def utilisation(account: AccountSnapshot, limits: Mapping[str, Any], buckets: BucketView | None) -> dict[str, Any]:
    """How much of each limit the account is using now."""
    equity = account.equity_usdc

    def share(value: float) -> float | None:
        return value / equity if equity > 0 else None

    def of_limit(value: float | None, limit: float) -> float | None:
        return None if value is None else value / limit

    loss = max(0.0, -account.day_pnl_usdc)
    gross = share(account.gross_exposure_usdc)
    symbol_limit, bucket_limit = limits["max_symbol_exposure_fraction"], limits["max_bucket_exposure_fraction"]
    groups = []
    if buckets is not None:
        for group in buckets.groups:
            exposure = sum(account.exposure_by_symbol.get(s, 0.0) for s in group)
            groups.append({"members": list(group), "exposure_usdc": exposure, "fraction_of_equity": share(exposure),
                           "limit": bucket_limit, "fraction_of_limit": of_limit(share(exposure), bucket_limit)})
    ungrouped = sorted(s for s in account.exposure_by_symbol if buckets is None or s not in buckets.grouped())
    return {
        "daily_loss": {"loss_usdc": loss, "limit_usdc": limits["daily_loss_limit_usdc"], "fraction_of_limit": loss / limits["daily_loss_limit_usdc"]},
        "drawdown": {"fraction": account.drawdown_fraction, "limit": limits["max_drawdown_fraction"],
                     "fraction_of_limit": account.drawdown_fraction / limits["max_drawdown_fraction"]},
        "gross_exposure": {"exposure_usdc": account.gross_exposure_usdc, "fraction_of_equity": gross,
                           "limit": limits["max_gross_exposure_fraction"], "fraction_of_limit": of_limit(gross, limits["max_gross_exposure_fraction"])},
        "symbols": [{"symbol": s, "exposure_usdc": v, "fraction_of_equity": share(v), "limit": symbol_limit,
                     "fraction_of_limit": of_limit(share(v), symbol_limit)} for s, v in account.exposure_by_symbol.items()],
        "buckets": groups,
        "unmeasured_open_symbols": ungrouped,
        "positions": {"open": len(account.marks), "limit": limits["max_concurrent_positions"]},
        "marks": {"oldest_age_s": account.oldest_mark_age_s(), "limit_s": limits["max_mark_age_s"]},
    }
