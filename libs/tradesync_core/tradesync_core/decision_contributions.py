"""Split one stored paper decision into what each feature and block contributed.

The producer stores its full reasoning with every decision (``paper_signal_v1``):
the directional contributors that set the side, every feature admitted for
scoring with its block, and each block's weight and quality. Nothing here
re-normalises a feature. It divides the recorded totals among the readings that
produced them, so the parts add back up to what was decided.

Two kinds of contribution are kept apart because they answer different
questions:

``directional``  a feature the catalog marks directional. Its contribution is its
                 share of the directional score: positive pulls LONG, negative
                 pulls SHORT. The shares sum to the directional score.
``suitability``  any other admitted feature. Its contribution is its share of the
                 blended suitability score: positive reads conditions as
                 favourable for taking a call, negative as unfavourable. It
                 never set a side.

A block containing a directional feature is judged by the directional pull of
its members; any other block by its share of the suitability score. A block with
no admitted evidence has no stance and is omitted.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

DIRECTIONAL = "directional"
SUITABILITY = "suitability"


@dataclass(frozen=True)
class Contribution:
    """One feature's or block's recorded pull on a decision."""

    key: str
    block: str
    role: str
    score: float
    quality: float
    weight: float
    contribution: float


@dataclass(frozen=True)
class DecisionContributions:
    direction: str
    directional_score: float | None
    features: tuple[Contribution, ...]
    blocks: tuple[Contribution, ...]
    rulebook_version: str | None
    rulebook_digest: str | None


def _number(value: Any) -> float | None:
    # Exact class checks: bool is excluded (its class is bool, not int), and a
    # stored decision is plain JSON, so no numeric subclass can appear. This
    # runs a hundred thousand times in a backfill; ABC checks cost seconds.
    if value.__class__ is float or value.__class__ is int:
        return float(value) if math.isfinite(value) else None
    return None


def _mapping(value: Any) -> dict[str, Any]:
    """Stored decisions are decoded JSON: objects arrive as plain dicts."""
    return value if isinstance(value, dict) else {}


def _directional_features(
    evidence: Mapping[str, Any], block_of: Mapping[str, str]
) -> list[Contribution]:
    contributors = _mapping(evidence.get("directional")).get("contributors") or []
    readings = []
    for item in contributors:
        item = _mapping(item)
        score, quality = _number(item.get("score")), _number(item.get("quality"))
        weight = _number(item.get("weight"))
        if not item.get("feature_id") or score is None or quality is None:
            continue
        readings.append((str(item["feature_id"]), score, quality, 1.0 if weight is None else weight))
    total = sum(quality * weight for _, _, quality, weight in readings)
    return [
        Contribution(
            key=feature_id,
            block=block_of.get(feature_id, "unknown"),
            role=DIRECTIONAL,
            score=score,
            quality=quality,
            weight=weight,
            contribution=round(score * quality * weight / total, 12) if total > 0 else 0.0,
        )
        for feature_id, score, quality, weight in readings
    ]


def _suitability_features(
    admitted: list[Mapping[str, Any]],
    blocks: Mapping[str, Any],
    directional_ids: set[str],
) -> list[Contribution]:
    coverage = sum(_number(_mapping(d).get("weighted_quality")) or 0.0 for d in blocks.values())
    in_block: dict[str, float] = {}
    for item in admitted:
        in_block[item["block"]] = in_block.get(item["block"], 0.0) + item["quality"]
    out = []
    for item in admitted:
        if item["feature_id"] in directional_ids:
            continue
        weighted_quality = _number(_mapping(blocks.get(item["block"])).get("weighted_quality")) or 0.0
        block_total = in_block.get(item["block"], 0.0)
        share = 0.0
        if coverage > 0 and block_total > 0:
            share = weighted_quality * (item["score"] * item["quality"] / block_total) / coverage
        out.append(
            Contribution(
                key=item["feature_id"],
                block=item["block"],
                role=SUITABILITY,
                score=item["score"],
                quality=item["quality"],
                weight=1.0,
                contribution=round(share, 12),
            )
        )
    return out


def _block_contributions(
    blocks: Mapping[str, Any], features: list[Contribution]
) -> list[Contribution]:
    coverage = sum(_number(_mapping(d).get("weighted_quality")) or 0.0 for d in blocks.values())
    out = []
    for block in sorted(blocks):
        detail = _mapping(blocks[block])
        score, quality = _number(detail.get("score")), _number(detail.get("quality"))
        weight = _number(detail.get("weight")) or 0.0
        weighted_quality = _number(detail.get("weighted_quality")) or 0.0
        if score is None or quality is None or quality <= 0:
            continue
        members = [f for f in features if f.block == block and f.role == DIRECTIONAL]
        if members:
            role, share = DIRECTIONAL, sum(f.contribution for f in members)
        else:
            role = SUITABILITY
            share = weighted_quality * score / coverage if coverage > 0 else 0.0
        out.append(Contribution(block, block, role, score, quality, weight, round(share, 12)))
    return out


def contributions_from_decision(decision: Mapping[str, Any]) -> DecisionContributions:
    """Every feature's and block's contribution to one stored decision."""

    decision = _mapping(decision)
    evidence = _mapping(decision.get("evidence"))
    admitted = []
    for item in decision.get("contributing_features") or []:
        item = _mapping(item)
        score, quality = _number(item.get("score")), _number(item.get("data_quality"))
        if item.get("feature_id") and score is not None and quality is not None:
            admitted.append(
                {
                    "feature_id": str(item["feature_id"]),
                    "block": str(item.get("block") or "unknown"),
                    "score": score,
                    "quality": quality,
                }
            )
    block_of = {item["feature_id"]: item["block"] for item in admitted}
    blocks = _mapping(evidence.get("contributions"))

    directional = _directional_features(evidence, block_of)
    suitability = _suitability_features(admitted, blocks, {f.key for f in directional})
    features = sorted(directional + suitability, key=lambda f: (-abs(f.contribution), f.key))

    return DecisionContributions(
        direction=str(decision.get("direction") or "NONE"),
        directional_score=_number(decision.get("directional_score")),
        features=tuple(features),
        blocks=tuple(_block_contributions(blocks, directional)),
        rulebook_version=evidence.get("rulebook_version"),
        rulebook_digest=evidence.get("rulebook_digest"),
    )
