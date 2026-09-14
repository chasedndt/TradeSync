"""Environment settings shared by the core scorer's loops and endpoints."""

import os

# Env vars
PG_DSN = os.getenv("PG_DSN", "postgresql://tradesync:CHANGE_ME@localhost:5432/tradesync")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
SCORING_INTERVAL = int(os.getenv("SCORING_INTERVAL", "60"))
# One symbol list for the whole stack: MARKET_SYMBOLS, as market-data reads it.
# The scorer speaks in bare coins, so the -PERP suffix is dropped here rather
# than kept as a second, divergent list.
SYMBOLS = [
    s.strip().replace("-PERP", "")
    for s in os.getenv("MARKET_SYMBOLS", os.getenv("SYMBOLS", "BTC,ETH,SOL")).split(",")
    if s.strip()
]

# The regime path is the native Hyperliquid paper pipeline. The legacy
# events-table path below remains importable for replay of historical rows,
# but it is no longer what the running loop produces.
REGIME_PAPER_ENABLED = os.getenv("REGIME_PAPER_ENABLED", "true").lower() == "true"
# The fastest catalog feature samples every 60s, so a shorter cycle would
# re-read the same evidence and fan out history requests for nothing.
REGIME_CYCLE_INTERVAL = int(os.getenv("REGIME_CYCLE_INTERVAL", "60"))
MINIMUM_COVERAGE_TO_EMIT = float(os.getenv("MINIMUM_COVERAGE_TO_EMIT", "0.30"))
DIRECTION_DEADBAND = float(os.getenv("DIRECTION_DEADBAND", "0.05"))
MAXIMUM_EVIDENCE_AGE_MS = int(os.getenv("MAXIMUM_EVIDENCE_AGE_MS", "120000"))
