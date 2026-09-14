"""Read regime evidence from the State API.

The regime engine is the single place that normalizes features. This service
asks it for the normalised readings and their evaluation under the rulebook
file rather than recomputing any of it. When an operator has adopted a learned
rulebook, app/active_weights.py re-weights those same readings with the shared
composition, so a live verdict and a Regime Lab comparison of the same window
differ only by the recorded, declared rulebook.

An unreachable State API is reported as unavailable evidence, never as a zero
score. A zero would look like a measured neutral reading; unavailable evidence
correctly produces no paper signal at all.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import httpx

STATE_API_URL = os.getenv("STATE_API_URL", "http://state-api:8000")
REGIME_OVERVIEW_TIMEOUT_SECONDS = float(
    os.getenv("REGIME_OVERVIEW_TIMEOUT_SECONDS", "10.0")
)


@dataclass(frozen=True)
class RegimeEvidence:
    """One regime read, or an explained failure to obtain one."""

    available: bool
    evaluation: dict[str, Any] = field(default_factory=dict)
    feature_results: list[dict[str, Any]] = field(default_factory=list)
    catalog: dict[str, Any] = field(default_factory=dict)
    directional: dict[str, Any] = field(default_factory=dict)
    source_status: dict[str, Any] = field(default_factory=dict)
    reason: str = ""


async def fetch_regime_evidence(
    symbol: str,
    venue: str = "hyperliquid",
    state_api_url: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> RegimeEvidence:
    """Fetch the baseline evaluation and per-feature evidence for one symbol."""

    url = f"{(state_api_url or STATE_API_URL).rstrip('/')}/state/regime-lab/overview"
    owns_client = client is None
    client = client or httpx.AsyncClient()
    try:
        response = await client.get(
            url,
            params={"venue": venue, "symbol": symbol},
            timeout=REGIME_OVERVIEW_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        return RegimeEvidence(available=False, reason=f"regime_read_failed: {exc}")
    finally:
        if owns_client:
            await client.aclose()

    evaluation = payload.get("baseline_evaluation")
    if not isinstance(evaluation, dict) or not evaluation:
        return RegimeEvidence(
            available=False,
            reason="regime overview returned no baseline evaluation",
        )

    source_status = payload.get("source_status") or {}
    if source_status.get("status") != "live":
        return RegimeEvidence(
            available=False,
            source_status=source_status,
            reason=(
                "market observations are "
                f"{source_status.get('status', 'unknown')}, so the evaluation "
                "does not describe current market conditions"
            ),
        )

    return RegimeEvidence(
        available=True,
        evaluation=evaluation,
        feature_results=list(payload.get("feature_results") or []),
        catalog=dict(payload.get("catalog") or {}),
        directional=dict(payload.get("directional_evidence") or {}),
        source_status=dict(source_status),
    )
