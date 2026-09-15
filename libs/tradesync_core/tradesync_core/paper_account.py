"""Managed-paper account figures: marks, equity, exposure, UTC-day P&L and drawdown.

Cash is the ledger balance: starting capital plus realised results
(``paper_account_ledger``). An open position is marked at its latest received
executable-side observation after the fees and funding it would pay to close
there, so equity is what the paper account would hold if everything closed at
those observations. A position not yet observed is marked at its entry price
less round-trip fees, and its mark says so.

Day P&L for a UTC day is realised results booked that day plus the change in
unrealised results across it: equity at the end of the day less equity at its
start, with nothing assumed between observations.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

DAY_S = 86400


def _finite(state: Mapping[str, Any], key: str, *, positive: bool = False) -> float:
    value = state.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or (positive and value <= 0):
        raise ValueError(f"Open paper position lacks a valid {key}")
    return float(value)


@dataclass(frozen=True)
class Mark:
    position_id: str
    symbol: str
    side: str
    quantity: float
    mark_price: float
    notional_usdc: float
    unrealised_usdc: float
    marked_at: float
    source: str  # observed_exit_side | entry_less_round_trip_fees

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def mark(position_id: Any, symbol: str, state: Mapping[str, Any]) -> Mark:
    quantity = _finite(state, "quantity", positive=True)
    if state.get("net_estimate_usdc") is not None and state.get("mark_exit_price") is not None:
        price = _finite(state, "mark_exit_price", positive=True)
        unrealised, source = _finite(state, "net_estimate_usdc"), "observed_exit_side"
    else:
        price = _finite(state, "entry_price", positive=True)
        unrealised, source = -2 * _finite(state, "entry_fee_usdc"), "entry_less_round_trip_fees"
    return Mark(str(position_id), symbol, str(state.get("side")), quantity, price, quantity * price,
                unrealised, _finite(state, "last_quote_time", positive=True), source)


def utc_day_start(now_s: float) -> float:
    return math.floor(now_s / DAY_S) * DAY_S


def utc_day(at_s: float) -> str:
    return datetime.fromtimestamp(at_s, timezone.utc).date().isoformat()


@dataclass(frozen=True)
class AccountSnapshot:
    as_of: float
    starting_capital_usdc: float
    cash_usdc: float
    unrealised_usdc: float
    equity_usdc: float
    gross_exposure_usdc: float
    exposure_by_symbol: dict[str, float]
    marks: tuple[Mark, ...]
    peak_equity_usdc: float
    drawdown_usdc: float
    drawdown_fraction: float
    day_start: float
    realised_today_usdc: float
    unrealised_at_day_start_usdc: float
    day_pnl_usdc: float

    def oldest_mark_age_s(self) -> float | None:
        return max((self.as_of - m.marked_at for m in self.marks), default=None)

    def as_dict(self) -> dict[str, Any]:
        body = asdict(self)
        body["marks"] = [m.as_dict() for m in self.marks]
        body["oldest_mark_age_s"] = self.oldest_mark_age_s()
        return body


def snapshot(*, now_s: float, starting_capital: Any, cash: Any, stored_peak: Any, marks: Iterable[Mark],
             realised_today: Any, unrealised_at_day_start: Any) -> AccountSnapshot:
    marks = tuple(marks)
    unrealised = sum(m.unrealised_usdc for m in marks)
    equity = float(cash) + unrealised
    exposure: dict[str, float] = {}
    for m in marks:
        exposure[m.symbol] = exposure.get(m.symbol, 0.0) + m.notional_usdc
    peak = max(float(stored_peak), equity)
    drawdown = peak - equity
    realised = float(realised_today)
    opening = float(unrealised_at_day_start)
    return AccountSnapshot(
        as_of=now_s, starting_capital_usdc=float(starting_capital), cash_usdc=float(cash),
        unrealised_usdc=unrealised, equity_usdc=equity, gross_exposure_usdc=sum(exposure.values()),
        exposure_by_symbol=exposure, marks=marks, peak_equity_usdc=peak, drawdown_usdc=drawdown,
        drawdown_fraction=drawdown / peak if peak > 0 else 1.0, day_start=utc_day_start(now_s),
        realised_today_usdc=realised, unrealised_at_day_start_usdc=opening,
        day_pnl_usdc=realised + unrealised - opening,
    )


def day_boundaries(now_s: float, days: int) -> list[float]:
    """Start of each of the last ``days`` UTC days (today last), plus the end of yesterday."""
    today = utc_day_start(now_s)
    return [today - DAY_S * i for i in range(days - 1, -1, -1)]


def daily_pnl(*, now_s: float, days: int, realised: Iterable[tuple[float, float]],
              unrealised_at: Mapping[float, float], unrealised_now: float) -> list[dict[str, Any]]:
    """P&L per UTC day, today last: realised in the day plus the change in unrealised across it.

    ``unrealised_at`` maps each day boundary to the total unrealised result of
    the positions open at that instant, from their latest observation at or
    before it. A boundary with no open position is zero.
    """
    today = utc_day_start(now_s)
    booked = list(realised)
    rows = []
    for start in day_boundaries(now_s, days):
        end = start + DAY_S
        realised_in_day = sum(amount for at, amount in booked if start <= at < end)
        opening = unrealised_at.get(start, 0.0)
        closing = unrealised_now if start == today else unrealised_at.get(end, 0.0)
        rows.append({"day": utc_day(start), "realised_usdc": realised_in_day,
                     "unrealised_change_usdc": closing - opening,
                     "pnl_usdc": realised_in_day + closing - opening, "complete": start != today})
    return rows
