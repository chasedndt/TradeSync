"""How the market measurably reacted to past occurrences of a scheduled event.

This is the honest form of "how will the market react to CPI": not a
prediction, but the record. For each past release of an event kind, the move
from the last hourly close at or before the release to the close H hours
later is measured on Hyperliquid candles, beside the same move on ordinary
days at the same time of day. The ratio says whether the event expands
volatility; the share of up moves says whether it has leaned a direction.
With a handful of occurrences neither is a law, and the output says how many
there were.

Pure: candles and instants in, numbers out. Fetching lives in state-api.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Iterable, Mapping, Sequence

HORIZONS_H = (1, 4, 24)
MIN_OCCURRENCES = 4
HOUR = 3600


@dataclass(frozen=True)
class EventKind:
    key: str
    label: str
    release_id: int | None
    et_hour: int
    et_minute: int
    patterns: tuple[str, ...]
    query: str
    source_url: str
    fixed_dates: tuple[str, ...] = field(default_factory=tuple)
    # Calendar country codes this kind is measured for; every kind here is a US release.
    countries: tuple[str, ...] = ("USD", "US")

    def matches(self, title: str) -> bool:
        return any(re.search(p, title, re.IGNORECASE) for p in self.patterns)


FED_CALENDAR = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"

EVENT_KINDS: dict[str, EventKind] = {k.key: k for k in (
    EventKind("fomc", "FOMC rate decision", None, 14, 0,
              (r"\bFOMC\b", r"federal funds rate", r"fed interest rate decision", r"fomc statement"),
              '("FOMC" OR "Federal Reserve") "interest rates"', FED_CALENDAR,
              # Decision days (second day of each meeting), from the Fed's published calendar.
              ("2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17", "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09")),
    EventKind("cpi", "US CPI", 10, 8, 30, (r"\bCPI\b", r"consumer price"), '"consumer price index" inflation',
              "https://www.bls.gov/cpi/"),
    EventKind("ppi", "US PPI", 46, 8, 30, (r"\bPPI\b", r"producer price"), '"producer price index"', "https://www.bls.gov/ppi/"),
    EventKind("nfp", "US jobs report (NFP)", 50, 8, 30, (r"non-?farm", r"employment situation", r"unemployment rate"),
              '"nonfarm payrolls" jobs report', "https://www.bls.gov/ces/"),
    EventKind("retail_sales", "US retail sales", 9, 8, 30, (r"retail sales", r"sales for retail"), '"retail sales" US Census',
              "https://www.census.gov/retail/"),
    EventKind("gdp", "US GDP", 53, 8, 30, (r"\bGDP\b",), '"GDP" US economy BEA', "https://www.bea.gov/data/gdp"),
    EventKind("pce", "US PCE inflation", 54, 8, 30, (r"\bPCE\b", r"personal income", r"personal spending"),
              '"PCE" inflation personal income', "https://www.bea.gov/data/income-saving/personal-income"),
    EventKind("jobless_claims", "US jobless claims", 180, 8, 30, (r"jobless claims", r"unemployment claims", r"unemployment insurance weekly claims"),
              '"jobless claims"', "https://www.dol.gov/ui/data.pdf"),
)}


def kind_for_title(title: str) -> EventKind | None:
    for kind in EVENT_KINDS.values():
        if kind.matches(title):
            return kind
    return None


def kind_for_event(event: Mapping[str, Any]) -> EventKind | None:
    """The kind of a calendar event, only when its title, country and (for FOMC) date all fit.

    Calendars reuse titles: Canada and Switzerland publish a "CPI m/m" or
    "PPI m/m" too, and FRED lists an "FOMC Press Release" entry every day. By
    title alone, US CPI's record would be pinned on Canada's release and the
    FOMC decision on an ordinary day. An event without a country is taken as
    the calendar's own (the FRED feed is US-only).
    """
    kind = kind_for_title(str(event.get("title") or ""))
    if kind is None:
        return None
    country = str(event.get("country") or "").upper()
    if country and country not in kind.countries:
        return None
    if kind.fixed_dates and str(event.get("scheduled_at") or "")[:10] not in kind.fixed_dates:
        return None
    return kind


def release_instant_s(day: date, kind: EventKind, tz) -> int:
    """The release time as epoch seconds, from a date and the kind's US Eastern time."""
    local = datetime.combine(day, time(kind.et_hour, kind.et_minute), tzinfo=tz)
    return int(local.astimezone(timezone.utc).timestamp())


def _by_close(candles: Iterable[Mapping[str, Any]]) -> dict[int, Mapping[str, Any]]:
    """1h candles keyed by close time (open time + one hour)."""
    return {int(c["time"]) + HOUR: c for c in candles if isinstance(c.get("time"), (int, float))}


def window_move(by_close: Mapping[int, Mapping[str, Any]], instant_s: int, hours: int) -> dict[str, float] | None:
    """Move from the last hourly close at or before the instant to the close ``hours`` later.

    A release at 08:30 is measured from the 08:00 close to the close that
    covers the release plus ``hours``; one on the hour from that hour's close.
    Also the largest excursion either way inside the window.
    """
    entry_t = instant_s - (instant_s % HOUR)
    exit_t = entry_t + hours * HOUR + (HOUR if instant_s % HOUR else 0)
    entry = by_close.get(entry_t)
    exit_ = by_close.get(exit_t)
    if not entry or not exit_:
        return None
    base = float(entry["close"])
    if base <= 0:
        return None
    highs, lows = [], []
    t = entry_t + HOUR
    while t <= exit_t:
        c = by_close.get(t)
        if c is None:
            return None  # a gap inside the window: no measurement rather than a partial one
        highs.append(float(c["high"]))
        lows.append(float(c["low"]))
        t += HOUR
    move = (float(exit_["close"]) - base) / base * 100
    rng = max(max(highs) - base, base - min(lows)) / base * 100
    return {"move_pct": move, "range_pct": rng}


def baseline_moves(by_close: Mapping[int, Mapping[str, Any]], instants: Sequence[int], hours: int,
                   exclude: Sequence[int], exclusion_h: int = 24) -> list[float]:
    """Absolute moves at the same time of day on days with no scheduled release nearby."""
    if not instants or not by_close:
        return []
    seconds_of_day = instants[0] % 86400
    first = min(by_close) - HOUR
    last = max(by_close)
    day = first - (first % 86400) + seconds_of_day
    blocked = sorted(exclude)
    out: list[float] = []
    while day <= last:
        if not any(abs(day - e) < exclusion_h * HOUR for e in blocked):
            m = window_move(by_close, day, hours)
            if m is not None:
                out.append(abs(m["move_pct"]))
        day += 86400
    return out


def profile(kind: EventKind, instants: Sequence[int], candles: Sequence[Mapping[str, Any]],
            all_event_instants: Sequence[int]) -> dict[str, Any]:
    """Reaction statistics for one kind on one symbol."""
    by_close = _by_close(candles)
    horizons: dict[str, Any] = {}
    occurrences: dict[int, dict[str, Any]] = {}
    for h in HORIZONS_H:
        moves = []
        for t in instants:
            m = window_move(by_close, t, h)
            if m is None:
                continue
            moves.append(m)
            occurrences.setdefault(t, {"at": datetime.fromtimestamp(t, tz=timezone.utc).isoformat()})[f"move_{h}h_pct"] = round(m["move_pct"], 3)
        base = baseline_moves(by_close, instants, h, all_event_instants)
        abs_moves = [abs(m["move_pct"]) for m in moves]
        med = statistics.median(abs_moves) if abs_moves else None
        base_med = statistics.median(base) if base else None
        horizons[f"{h}h"] = {
            "n": len(moves),
            "median_abs_move_pct": round(med, 3) if med is not None else None,
            "median_range_pct": round(statistics.median([m["range_pct"] for m in moves]), 3) if moves else None,
            "baseline_median_abs_move_pct": round(base_med, 3) if base_med is not None else None,
            "baseline_days": len(base),
            "volatility_ratio": round(med / base_med, 2) if med is not None and base_med else None,
            "up_share": round(sum(1 for m in moves if m["move_pct"] > 0) / len(moves), 3) if moves else None,
            "mean_move_pct": round(statistics.fmean([m["move_pct"] for m in moves]), 3) if moves else None,
        }
    return {"kind": kind.key, "label": kind.label, "horizons": horizons,
            "occurrences": sorted(occurrences.values(), key=lambda o: o["at"], reverse=True)[:8]}


def guidance(kind_label: str, symbol_label: str, prof: Mapping[str, Any], horizon: str = "4h") -> str:
    """One plain sentence a trader can act on, with its sample size."""
    h = (prof.get("horizons") or {}).get(horizon) or {}
    n = h.get("n") or 0
    if n < MIN_OCCURRENCES:
        return f"{kind_label}: only {n} past release(s) measured on {symbol_label}; too few to judge its reaction."
    ratio, up, med, rng = h.get("volatility_ratio"), h.get("up_share"), h.get("median_abs_move_pct"), h.get("median_range_pct")
    vol = (f"moved {symbol_label} {med:.2f}% over {horizon} (median of {n}), {ratio:.1f}× an ordinary {horizon}"
           if ratio else f"moved {symbol_label} {med:.2f}% over {horizon} (median of {n})")
    if up is not None and 0.35 <= up <= 0.65:
        lean = "with no consistent direction"
    elif up is not None:
        k = round(up * n)
        lean = f"up in {k} of {n}" if up > 0.5 else f"down in {n - k} of {n}"
    else:
        lean = ""
    if ratio and ratio >= 1.5:
        act = f"expect a volatility expansion: stand aside or cut size into the release, and give stops more than {rng:.2f}%."
    elif ratio and ratio <= 0.9:
        act = "it has not moved the market more than an ordinary day; no special handling measured."
    else:
        act = f"a modest effect; keep stops beyond the usual {rng:.2f}% range through the release."
    return f"{kind_label} has {vol}, {lean}; {act}".replace(", ;", ";")
