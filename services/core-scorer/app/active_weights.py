"""The paper scorer uses the operator-adopted rulebook, read every cycle.

The regime engine (state-api) normalises every feature and evaluates the
readings under the rulebook file. When an operator adopts a learned rulebook it
is recorded in ``regime_weight_activations``; this module makes each verdict use
it by re-weighting those same normalised readings with the shared composition
(``tradesync_core.rulebook_evidence``). Nothing is normalised twice, so a verdict
differs from the Regime Lab's file evaluation only by the declared rulebook.

Every problem falls back to the file weights the regime engine already applied,
and says why: no adopted rulebook, a stored rulebook that fails validation, a
feature catalog that no longer matches the engine's, or an unreadable database.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache

from tradesync_core.active_rulebook import ACTIVE_RULEBOOK_SQL, rulebook_from_config
from tradesync_core.market_features import FeatureCatalog, load_catalog
from tradesync_core.regime_weights import RulebookValidationError
from tradesync_core.rulebook_evidence import evaluate_rulebook_evidence

from .outcome_features import _catalog_path as catalog_path
from .regime_source import RegimeEvidence

NO_ADOPTED_RULEBOOK = "no adopted rulebook is active"


@dataclass(frozen=True)
class WeightsChoice:
    source: str  # "database" | "file"
    version: str | None
    reason: str

    @property
    def fell_back(self) -> bool:
        return self.source == "file" and self.reason != NO_ADOPTED_RULEBOOK


@lru_cache(maxsize=1)
def feature_catalog() -> FeatureCatalog:
    return load_catalog(catalog_path())


def _file(evidence: RegimeEvidence, reason: str) -> tuple[RegimeEvidence, WeightsChoice]:
    return evidence, WeightsChoice("file", evidence.evaluation.get("rulebook_version"), reason)


async def apply_active_rulebook(conn, evidence: RegimeEvidence) -> tuple[RegimeEvidence, WeightsChoice]:
    """``evidence`` re-weighted under the adopted rulebook, or unchanged with the reason why."""

    try:
        row = await conn.fetchrow(ACTIVE_RULEBOOK_SQL, evidence.evaluation.get("rulebook_id"))
    except Exception as exc:  # a missing table or a dropped connection must not stop verdicts
        return _file(evidence, f"active rulebook unreadable ({type(exc).__name__}); file weights used")
    if not row:
        return _file(evidence, NO_ADOPTED_RULEBOOK)
    try:
        rulebook = rulebook_from_config(row["config"])
    except (RulebookValidationError, ValueError, TypeError) as exc:
        return _file(evidence, f"adopted rulebook is invalid ({exc}); file weights used")
    try:
        catalog = feature_catalog()
    except (OSError, ValueError) as exc:
        return _file(evidence, f"feature catalog unavailable ({type(exc).__name__}); file weights used")
    if catalog.digest != evidence.catalog.get("digest"):
        return _file(evidence, "feature catalog differs from the regime engine's; file weights used")

    evaluation, directional = evaluate_rulebook_evidence(catalog, rulebook, evidence.feature_results)
    return (
        replace(evidence, evaluation=evaluation, directional=directional),
        WeightsChoice("database", rulebook.version, f"adopted rulebook {rulebook.version}"),
    )
