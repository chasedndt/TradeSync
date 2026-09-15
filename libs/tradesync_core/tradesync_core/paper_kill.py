"""The kill switch's close of one open paper position, through the managed-paper close.

The close is the lifecycle's own operator close on a fresh observed book: the exit
walks the displayed depth for the position's quantity, the taker fee is charged at that
fill, and funding is netted from the settled rows passed in (``funding_rows``). Only the
recorded rule differs: ``kill_switch``. A stop, target or expiry the same observation
fires is kept beside it as ``coincided_rule``.

When the displayed book cannot take the whole quantity the lifecycle does not assume a
fill: the exit stays owed (``pending_exit``) and fills at the first later observation
that can. The owed exit carries the ``kill_switch`` rule, so whichever observation fills
it records the kill switch. A missing, stale, out-of-order or one-sided book raises and
nothing changes.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from tradesync_core.managed_paper import advance

EXIT_REASON = "kill_switch"


def _labelled(record: Mapping[str, Any]) -> dict[str, Any]:
    natural = record.get("rule")
    labelled = {**record, "rule": EXIT_REASON}
    if natural not in (None, "operator_close", EXIT_REASON):
        labelled["coincided_rule"] = natural
    return labelled


def kill_close(position: Mapping[str, Any], book: Mapping[str, Any], now_s: float, *,
               funding_rows: Sequence[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """The position closed for the kill switch, or still open with the kill-switch exit owed."""
    if position.get("status") != "open":
        raise ValueError("Only an open paper position can be closed by the kill switch")
    result = advance(dict(position), book, now_s, manual_close=True, funding_rows=funding_rows)
    if result.get("status") == "closed":
        result["exit"] = _labelled(result["exit"])
        result["exit_reason"] = EXIT_REASON
    elif result.get("pending_exit"):
        result["pending_exit"] = _labelled(result["pending_exit"])
    else:
        raise ValueError("The lifecycle neither closed the position nor recorded an owed exit")
    return result
