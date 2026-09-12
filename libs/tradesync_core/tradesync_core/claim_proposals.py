"""Claims proposed by the advisory harness, checked before they count.

The rule extractor abstains on most agent prose. For those posts the harness
is asked one narrow question: *what directional calls does this post make?*
It answers in a shape that carries no authority — ``symbol``, ``stance``
(bullish or bearish), ``horizon_minutes`` and a verbatim ``quote`` — and the
answer is checked here:

- the symbol must be one the system tracks;
- the stance must be exactly bullish or bearish;
- the quote must appear verbatim in the post, so a proposal the harness
  invented cannot become a claim;
- the quote itself must not be negated or reporting (same rules as the rule
  extractor), so "not bullish" and "short resolved" are refused.

A claim that passes belongs to the post's source, under extractor
``harness_v1``. The harness is the reader, never the caller.
"""

from __future__ import annotations

import json
import re
from typing import Any, Mapping, Sequence

from .claim_extraction import (
    ALLOWED_HORIZONS,
    DEFAULT_HORIZON_MINUTES,
    Claim,
    NoClaim,
    _NEGATED,
    _REPORTING,
    normalise_symbol,
)

EXTRACTOR = "harness_v1"
INTENT = "extract_claims"
MAX_POST_CHARS = 6_000
MAX_PROPOSALS = 8
_STANCE = {"bullish": "LONG", "bearish": "SHORT"}
_JSON_BLOCK = re.compile(r"\[.*\]", re.DOTALL)


def proposal_prompt(agent: str, text: str) -> str:
    """The question put to the harness. It asks what the post said, not what to do."""
    body = text[:MAX_POST_CHARS]
    return (
        "Read the post below, written by the source named "
        f"'{agent}'. List every explicit directional call the POST ITSELF makes about a "
        "crypto asset: the author saying it is bullish or bearish on a specific asset now. "
        "Do not infer, do not add your own view, and ignore reports about past trades or "
        "outcomes. Answer with a JSON array only, no prose. Each element: "
        '{"symbol": "<ticker as written>", "stance": "bullish" | "bearish", '
        '"horizon_minutes": 15 | 60 | 240, "quote": "<a short verbatim phrase from the post '
        'that states the call>"}. If the post makes no such call, answer [] .\n\n'
        f"POST:\n{body}"
    )


def _horizon(value: Any) -> int:
    try:
        h = int(value)
    except (TypeError, ValueError):
        return DEFAULT_HORIZON_MINUTES
    return h if h in ALLOWED_HORIZONS else DEFAULT_HORIZON_MINUTES


def _normalise_ws(s: str) -> str:
    return " ".join(s.split()).lower()


def parse_proposals(
    content: str,
    *,
    source: str,
    source_id: str,
    text: str,
    claimed_at_ms: int,
) -> list[Claim] | NoClaim:
    """The harness answer -> checked claims, or the reason none survived."""
    m = _JSON_BLOCK.search(content or "")
    if not m:
        return NoClaim("harness answer contained no JSON array")
    try:
        proposals = json.loads(m.group(0))
    except ValueError:
        return NoClaim("harness answer was not valid JSON")
    if not isinstance(proposals, list):
        return NoClaim("harness answer was not a list")
    if not proposals:
        return NoClaim("harness read no directional call in the post")

    haystack = _normalise_ws(text)
    claims: dict[str, Claim] = {}
    rejected: list[str] = []
    for p in proposals[:MAX_PROPOSALS]:
        if not isinstance(p, Mapping):
            rejected.append("not an object")
            continue
        symbol = normalise_symbol(str(p.get("symbol") or ""))
        direction = _STANCE.get(str(p.get("stance") or "").strip().lower())
        quote = str(p.get("quote") or "").strip()
        if symbol is None:
            rejected.append(f"symbol '{p.get('symbol')}' not tracked")
            continue
        if direction is None:
            rejected.append("stance not bullish/bearish")
            continue
        if len(quote) < 6 or _normalise_ws(quote) not in haystack:
            rejected.append("quote not found verbatim in the post")
            continue
        if _NEGATED.search(quote) or _REPORTING.search(quote):
            rejected.append("quote is negated or reports a past trade")
            continue
        if symbol in claims and claims[symbol].direction != direction:
            rejected.append(f"{symbol} proposed both ways")
            claims.pop(symbol, None)
            continue
        claims[symbol] = Claim(source, source_id, symbol, direction, _horizon(p.get("horizon_minutes")), claimed_at_ms, EXTRACTOR, quote[:240])
    if not claims:
        return NoClaim("every proposal was rejected: " + "; ".join(rejected[:4]))
    return list(claims.values())
