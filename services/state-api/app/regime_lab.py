"""Source-backed, paper-only Regime Lab orchestration for the State API."""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any, Mapping

import httpx

from tradesync_core.market_features import (
    FeatureCatalog,
    FeatureValidationError,
    load_catalog,
    normalize_feature,
)
from tradesync_core.regime_lab import (
    RegimeLabValidationError,
    aggregate_feature_evidence,
    assess_learning_gate,
    build_challenger_rulebook,
    compare_experiment,
)
from tradesync_core.regime_weights import RegimeRulebook, evaluate_blocks, load_rulebook


def _repo_or_container_path(relative: str, container_path: str) -> Path:
    configured = os.getenv(relative.upper().replace("/", "_").replace(".", "_"))
    candidates = [
        Path(configured) if configured else None,
        Path(container_path),
        Path(__file__).resolve().parents[3] / relative,
    ]
    for candidate in candidates:
        if candidate and candidate.is_file():
            return candidate
    raise FileNotFoundError(f"required Regime Lab configuration not found: {relative}")


def default_catalog_path() -> Path:
    configured = os.getenv("MARKET_FEATURE_CATALOG_PATH")
    if configured:
        return Path(configured)
    return _repo_or_container_path(
        "config/features/market-feature-catalog-v1.json",
        "/app/config/features/market-feature-catalog-v1.json",
    )


def default_rulebook_path() -> Path:
    configured = os.getenv("REGIME_RULEBOOK_PATH")
    if configured:
        return Path(configured)
    return _repo_or_container_path(
        "config/regime/regime-rulebook-v1.json",
        "/app/config/regime/regime-rulebook-v1.json",
    )


class RegimeLabEngine:
    """Load canonical configs and evaluate source-backed paper challengers."""

    def __init__(
        self,
        catalog_path: Path | None = None,
        rulebook_path: Path | None = None,
    ):
        self.catalog: FeatureCatalog = load_catalog(catalog_path or default_catalog_path())
        self.baseline: RegimeRulebook = load_rulebook(rulebook_path or default_rulebook_path())

    def configuration_summary(self) -> dict[str, Any]:
        return {
            "mode": "paper_shadow",
            "execution_authority": False,
            "baseline": {
                "rulebook_id": self.baseline.rulebook_id,
                "version": self.baseline.version,
                "status": self.baseline.data["status"],
                "digest": self.baseline.digest,
                "weights": self.baseline.weights,
                "weight_sum": round(sum(self.baseline.weights.values()), 12),
                "compression_k": self.baseline.compression_k,
                "activation_mode": self.baseline.data["governance"]["activation_mode"],
            },
            "catalog": {
                "catalog_id": self.catalog.data["catalog_id"],
                "version": self.catalog.version,
                "digest": self.catalog.digest,
                "feature_count": len(self.catalog.features),
            },
            "learning": {
                "module": "Year 2 Probability and Statistics",
                "class": "Regime Lab 02 - weights, coverage, and challenger controls",
                "arithmetic_prompt": "What must all block weights add to?",
                "interpretation_prompt": (
                    "Explain why data coverage describes evidence availability, not the "
                    "probability that a trade wins."
                ),
            },
        }

    def normalize_observations(
        self,
        observations: list[Mapping[str, Any]],
        histories: Mapping[str, list[Mapping[str, Any]]],
        evaluated_at_ms: int | None = None,
    ) -> list[dict[str, Any]]:
        now_ms = evaluated_at_ms or int(time.time() * 1000)
        observation_by_id = {
            str(item.get("feature_id")): item
            for item in observations
            if item.get("feature_id")
        }
        results: list[dict[str, Any]] = []
        for feature_id, definition in self.catalog.features.items():
            observation = observation_by_id.get(feature_id)
            common = {
                "feature_id": feature_id,
                "block": definition["block"],
                "unit": definition["unit"],
                "provenance": definition["provenance"],
                "source_authority": definition["source_authority"],
                "decision_role": definition["decision_role"],
                "sampling_interval_ms": definition["sampling_interval_ms"],
                "minimum_history_points": definition["minimum_history_points"],
                "lookback_points": definition["lookback_points"],
            }
            if observation is None:
                results.append(
                    {
                        **common,
                        "availability": definition["availability"],
                        "status": "unavailable",
                        "current_value": None,
                        "score": None,
                        "data_quality": 0.0,
                        "scoring_allowed": False,
                        "reason": (
                            f"no current admitted observation; catalog state is "
                            f"{definition['availability']}"
                        ),
                    }
                )
                continue

            current_ts = int(observation["observed_at_ms"])
            history = sorted(
                (
                    {"ts": int(item["ts"]), "value": item["value"]}
                    for item in histories.get(feature_id, [])
                    if int(item["ts"]) < current_ts
                ),
                key=lambda item: item["ts"],
            )
            # A restarted sampler can expose duplicate timestamps from old data.
            deduped = {item["ts"]: item for item in history}
            request = {
                "feature_id": feature_id,
                "symbol": observation["symbol"],
                "timeframe": observation.get("timeframe", "snapshot"),
                "evaluated_at_ms": max(now_ms, current_ts),
                "current": {
                    "ts": current_ts,
                    "value": observation["value"],
                    "source_event_id": observation["source_event_id"],
                },
                "history": list(deduped.values()),
            }
            try:
                result = normalize_feature(self.catalog, request)
            except FeatureValidationError as exc:
                result = {
                    "feature_id": feature_id,
                    "status": "unavailable",
                    "current_value": observation.get("value"),
                    "score": None,
                    "data_quality": 0.0,
                    "scoring_allowed": False,
                    "reason": str(exc),
                }
            results.append({**common, **result})
        return results

    def build_overview(
        self,
        feature_results: list[Mapping[str, Any]],
        source_status: Mapping[str, Any],
    ) -> dict[str, Any]:
        evidence = aggregate_feature_evidence(
            self.catalog, self.baseline, feature_results
        )
        baseline_evaluation = evaluate_blocks(
            self.baseline,
            evidence.block_scores,
            evidence.data_quality,
            [],
        )
        return {
            **self.configuration_summary(),
            "source_status": dict(source_status),
            "feature_results": feature_results,
            "block_evidence": evidence.blocks,
            "baseline_evaluation": baseline_evaluation,
            "operator_action_required": (
                "Enter a testable hypothesis, a complete five-block weight set, "
                "the arithmetic answer, and your own coverage explanation."
            ),
        }

    def evaluate_request(
        self,
        payload: Mapping[str, Any],
        feature_results: list[Mapping[str, Any]],
    ) -> dict[str, Any]:
        evidence = aggregate_feature_evidence(
            self.catalog, self.baseline, feature_results
        )
        challenger = build_challenger_rulebook(
            self.baseline,
            payload.get("weights", {}),
            str(payload.get("version", "")),
            str(payload.get("hypothesis", "")),
        )
        learning = assess_learning_gate(
            payload.get("arithmetic_answer"), payload.get("reflection")
        )
        comparison = compare_experiment(
            self.baseline, challenger, evidence, payload.get("risk_flags", [])
        )
        return {
            "valid": True,
            "mode": "paper_shadow",
            "execution_authority": False,
            "hypothesis": str(payload["hypothesis"]).strip(),
            "evaluation_window": payload.get(
                "evaluation_window", "current_evidence_snapshot"
            ),
            "expected_effect": payload.get("expected_effect", "uncertain"),
            "weight_sum": round(sum(challenger.weights.values()), 12),
            "learning_gate": learning,
            "block_evidence": evidence.blocks,
            "comparison": comparison,
            "challenger_config": challenger.data,
            "challenger_digest": challenger.digest,
            "persistable": learning["complete"],
            "activation_available": False,
        }


async def collect_live_feature_results(
    engine: RegimeLabEngine,
    market_data_url: str,
    venue: str,
    symbol: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fetch current values and their server-sampled histories."""

    try:
        async with httpx.AsyncClient() as client:
            current_response = await client.get(
                f"{market_data_url}/features/{venue}/{symbol}", timeout=5.0
            )
            current_response.raise_for_status()
            observations = current_response.json().get("observations", [])

            normalized_ids = [
                item["feature_id"]
                for item in observations
                if engine.catalog.features.get(item["feature_id"], {}).get(
                    "normalization"
                )
                != "none"
            ]

            async def fetch_history(feature_id: str):
                response = await client.get(
                    f"{market_data_url}/feature-history/{venue}/{symbol}/{feature_id}",
                    params={"window": "7d"},
                    timeout=5.0,
                )
                response.raise_for_status()
                return feature_id, response.json().get("data", [])

            history_pairs = await asyncio.gather(
                *(fetch_history(feature_id) for feature_id in normalized_ids)
            )
            histories = dict(history_pairs)
            results = engine.normalize_observations(observations, histories)
            return results, {
                "status": "live",
                "provider": "market-data",
                "venue": venue,
                "symbol": symbol,
                "observation_count": len(observations),
                "history_source": "cadence_governed_redis_feature_series",
            }
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        results = engine.normalize_observations([], {})
        return results, {
            "status": "unavailable",
            "provider": "market-data",
            "venue": venue,
            "symbol": symbol,
            "observation_count": 0,
            "reason": str(exc),
        }


async def persist_experiment(
    conn,
    engine: RegimeLabEngine,
    payload: Mapping[str, Any],
    evaluation: Mapping[str, Any],
    created_by: str = "local-operator",
) -> str:
    """Persist immutable baseline/challenger configs and one draft experiment."""

    challenger = validate_rulebook(evaluation["challenger_config"])

    async def ensure_rulebook(rulebook: RegimeRulebook) -> str:
        row = await conn.fetchrow(
            """
            insert into regime_rulebooks (
              rulebook_id, version, schema_version, status, environment, horizon,
              config_digest, config, created_by
            ) values ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9)
            on conflict (config_digest) do nothing
            returning id
            """,
            rulebook.rulebook_id,
            rulebook.version,
            rulebook.data["schema_version"],
            rulebook.data["status"],
            rulebook.data["environment"],
            rulebook.data["horizon"],
            rulebook.digest,
            json.dumps(rulebook.data),
            created_by,
        )
        if row:
            return str(row["id"])
        existing = await conn.fetchrow(
            "select id from regime_rulebooks where config_digest=$1",
            rulebook.digest,
        )
        if not existing:
            raise RuntimeError("rulebook insert did not return or resolve an ID")
        return str(existing["id"])

    baseline_id = await ensure_rulebook(engine.baseline)
    challenger_id = await ensure_rulebook(challenger)
    row = await conn.fetchrow(
        """
        insert into regime_experiments (
          name, status, horizon, champion_rulebook_id, challenger_rulebook_id,
          hypothesis, evaluation_plan, results
        ) values ($1,'draft',$2,$3::uuid,$4::uuid,$5,$6::jsonb,$7::jsonb)
        returning id
        """,
        payload.get("name") or f"Regime Lab {challenger.version}",
        engine.baseline.data["horizon"],
        baseline_id,
        challenger_id,
        evaluation["hypothesis"],
        json.dumps(
            {
                "evaluation_window": evaluation["evaluation_window"],
                "expected_effect": evaluation["expected_effect"],
                "learning_gate": evaluation["learning_gate"],
                "operator_reflection": payload.get("reflection", ""),
                "mode": "paper_shadow",
            }
        ),
        json.dumps(
            {
                "comparison": evaluation["comparison"],
                "block_evidence": evaluation["block_evidence"],
                "source_snapshot_only": True,
            }
        ),
    )
    return str(row["id"])


# Imported late to keep the persistence function easy to unit test.
from tradesync_core.regime_weights import validate_rulebook  # noqa: E402
