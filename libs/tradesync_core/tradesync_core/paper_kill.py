"""The kill switch's close of one open paper position.

Closing uses the managed-paper lifecycle unchanged: the next received
executable-side quote with its adverse slippage, fees and funding. Only the
recorded reason differs. A missing, stale, out-of-order or thin book raises and
the position stays open for the next attempt; no price is ever assumed.
"""

from __future__ import annotations

from typing import Any, Mapping

from tradesync_core.managed_paper import advance

EXIT_REASON = "kill_switch"


def kill_close(position: Mapping[str, Any], book: Mapping[str, Any], now_s: float) -> dict[str, Any]:
    if position.get("status") != "open":
        raise ValueError("Only an open paper position can be closed by the kill switch")
    result = advance(dict(position), book, now_s, manual_close=True)
    if result.get("status") != "closed":
        raise ValueError("The lifecycle did not close the position")
    natural = result.get("exit_reason")
    result["exit_reason"] = EXIT_REASON
    if natural not in (None, "operator_close"):
        # A stop or target seen at the same observation: recorded, not substituted.
        result["kill_switch_coincided_with"] = natural
    return result
