"""Thin registry over one model per file.

``app/models.py`` and ``app/models/`` both existed. Python resolves a regular
module before a namespace-package directory, so ``app.models`` always meant the
flat file and every ``from .models.market import ...`` raised
``'app.models' is not a package`` — in the test run and equally inside the
container, where ``app/ingest.py`` and ``app/collectors/hyperliquid.py`` were
therefore unimportable dead code.

``NormalizedEvent`` was also declared identically in both places. It now has one
definition; the names below stay importable from ``app.models`` exactly as
before.
"""

from .alert import TradingViewAlert
from .event import NormalizedEvent
from .market import MarketSnapshot

__all__ = ["TradingViewAlert", "NormalizedEvent", "MarketSnapshot"]
