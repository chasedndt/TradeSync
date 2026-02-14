"""
Symbol and venue normalization utilities.
Consolidated from the 3 identical normalize.py copies across services.
"""


def normalize_symbol(symbol: str) -> str:
    """
    Normalizes a trading symbol to BASE-PERP format.
    Accepts: BTCUSDT, BTC/USDT, BTC-PERP, btc-perp, BTC
    Returns: BTC-PERP
    """
    if not symbol:
        return symbol
    s = symbol.upper().strip()

    # 1. Handle slash separators first (before suffix replacement)
    s = s.replace("/", "")

    # 2. Handle common suffix replacements
    if s.endswith("USDT"):
        s = s[:-4] + "-PERP"
    elif s.endswith("USDC"):
        s = s[:-4] + "-PERP"

    # 3. Ensure -PERP suffix if not present
    if not s.endswith("-PERP"):
        if "-" in s:
            base = s.split("-")[0]
            s = f"{base}-PERP"
        else:
            s = f"{s}-PERP"

    return s


def normalize_venue(venue: str) -> str:
    """
    Normalizes venue names.
    Accepts: hl, hyperliquid, drift
    Returns: hyperliquid, drift
    """
    if not venue:
        return venue
    v = venue.lower().strip()
    if v == "hl":
        return "hyperliquid"
    return v
