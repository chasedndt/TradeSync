"""The horizons the outlook reads, from one hour to six months, and the bars each is measured on.

Every horizon gets the same analysis (trend, momentum, the record behind them,
the ordinary range, and every feature with its record and earned weight), read
on the bar a trader would use for it:

- short term: 1 hour and 4 hours on 15-minute bars; 8 hours and 1 day on
  hourly bars (Hyperliquid serves about 5,000 of each: 52 and 208 days);
- lower, medium and higher time frames: 3 days to 6 months on daily bars
  (the venue's history from 2020).

Lengths are counted in bars, so a "20-bar average" is 20 days on daily bars
and 5 hours on 15-minute bars; ``span`` turns them back into words.
"""

from __future__ import annotations

from dataclasses import dataclass

INTERVAL_SECONDS: dict[str, int] = {"15m": 900, "1h": 3600, "1d": 86400}
INTERVAL_WORDS: dict[str, str] = {"15m": "15-minute", "1h": "hourly", "1d": "daily"}


def span(bars: int, bar_seconds: int) -> str:
    """A length as it reads before a noun: ``20-day``, ``5-hour``, ``45-minute``."""
    seconds = bars * bar_seconds
    if seconds % 86400 == 0:
        return f"{seconds // 86400}-day"
    if seconds % 3600 == 0:
        return f"{seconds // 3600}-hour"
    return f"{seconds / 60:g}-minute"


def period(bars: int, bar_seconds: int) -> str:
    """A lookback as a phrase: ``year``, ``30 days``, ``day``, ``12 hours``."""
    days = bars * bar_seconds / 86400
    if days >= 360:
        return "year"
    if days >= 1 and float(days).is_integer():
        return "day" if days == 1 else f"{int(days)} days"
    return f"{bars * bar_seconds / 3600:g} hours"


@dataclass(frozen=True)
class Horizon:
    key: str
    label: str
    steps: int                      # bars ahead
    band: str
    interval: str                   # the bar the horizon is read on
    ma_bars: int                    # trend average
    vol_bars: int                   # realised volatility lookback
    rank_bars: int                  # volatility is ranked among this many bars, the latest included
    range_bars: int                 # range position lookback
    rsi_bars: int                   # RSI period
    participation: tuple[int, int]  # (recent, baseline) volume windows
    high_bars: int                  # drawdown is measured from the highest high of this many bars

    @property
    def bar_seconds(self) -> int:
        return INTERVAL_SECONDS[self.interval]

    @property
    def adjective(self) -> str:
        """``3-day``, ``4-hour``: the label as it reads before a noun."""
        number, unit = self.label.split(" ", 1)
        return f"{number}-{unit.removesuffix('s')}"

    def span(self, bars: int) -> str:
        return span(bars, self.bar_seconds)

    def period(self, bars: int) -> str:
        return period(bars, self.bar_seconds)


HORIZONS: tuple[Horizon, ...] = (
    Horizon("1h", "1 hour", 4, "short", "15m", 20, 96, 2880, 96, 14, (8, 96), 672),
    Horizon("4h", "4 hours", 16, "short", "15m", 48, 192, 2880, 384, 56, (16, 192), 1344),
    Horizon("8h", "8 hours", 8, "short", "1h", 24, 72, 720, 72, 14, (8, 72), 336),
    Horizon("1d", "1 day", 24, "short", "1h", 48, 168, 1440, 168, 56, (24, 168), 720),
    Horizon("3d", "3 days", 3, "lower", "1d", 20, 30, 366, 20, 14, (7, 30), 365),
    Horizon("1w", "1 week", 7, "lower", "1d", 20, 30, 366, 30, 14, (7, 30), 365),
    Horizon("2w", "2 weeks", 14, "medium", "1d", 50, 60, 366, 60, 14, (30, 90), 365),
    Horizon("1m", "1 month", 30, "medium", "1d", 50, 90, 366, 120, 14, (30, 90), 365),
    Horizon("3m", "3 months", 91, "higher", "1d", 200, 180, 366, 365, 98, (90, 365), 365),
    Horizon("6m", "6 months", 182, "higher", "1d", 200, 365, 366, 730, 98, (90, 365), 365),
)
BANDS: dict[str, str] = {
    "short": "Short term",
    "lower": "Lower time frame",
    "medium": "Medium time frame",
    "higher": "Higher time frame",
}
BY_KEY: dict[str, Horizon] = {h.key: h for h in HORIZONS}
