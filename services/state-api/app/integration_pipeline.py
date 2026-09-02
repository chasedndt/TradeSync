"""Inspectable runtime topology for TradeSync and its optional connectors.

The response deliberately separates live probes from repository contracts. A
component is never reported as connected merely because code or a document
exists for it.
"""

from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timezone
from typing import Any, Mapping

import httpx


HEALTHY_STATES = {"live", "healthy"}


def _recovery(
    kind: str,
    label: str,
    target: str,
    command: str | None = None,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "label": label,
        "target": target,
        "command": command,
    }


def _node(
    *,
    node_id: str,
    label: str,
    owner: str,
    tier: str,
    stage: str,
    status: str,
    required_for_tier_a: bool,
    authority: str,
    summary: str,
    evidence: list[str],
    missing: list[str],
    impact: str,
    recovery: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": node_id,
        "label": label,
        "owner": owner,
        "tier": tier,
        "stage": stage,
        "status": status,
        "required_for_tier_a": required_for_tier_a,
        "authority": authority,
        "summary": summary,
        "evidence": evidence,
        "missing": missing,
        "impact": impact,
        "recovery": recovery,
    }


def assemble_pipeline_status(
    *,
    probes: Mapping[str, Mapping[str, Any]],
    postgres: Mapping[str, Any],
    redis: Mapping[str, Any],
    catalog_feature_count: int,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a stable UI contract from explicit probe/configuration results."""

    market_health = probes.get("market_health", {})
    market_status = probes.get("market_status", {})
    market_features = probes.get("market_features", {})
    providers = market_status.get("data", {}).get("providers", [])
    hyperliquid_enabled = any(
        provider.get("venue") == "hyperliquid" and provider.get("enabled")
        for provider in providers
    )
    market_live = bool(market_health.get("ok") and hyperliquid_enabled)
    observation_count = int(market_features.get("data", {}).get("count", 0) or 0)
    market_latency = market_status.get("latency_ms")

    postgres_live = bool(postgres.get("ok"))
    redis_live = bool(redis.get("ok"))
    ingest_live = bool(probes.get("ingest_gateway", {}).get("ok"))
    scorer_live = bool(probes.get("core_scorer", {}).get("ok"))
    fusion_live = bool(probes.get("fusion_engine", {}).get("ok"))

    def probe_label(key: str) -> str:
        probe = probes.get(key, {})
        if probe.get("ok"):
            return "passed"
        if probe.get("configured") is False:
            return "not configured in this runtime"
        return "offline"

    latest_signal = postgres.get("latest_signal_ts")
    latest_opportunity = postgres.get("latest_opportunity_ts")
    regime_status = "partial" if market_live and observation_count else "offline"
    scorer_status = "live" if scorer_live and fusion_live else (
        "partial" if scorer_live or fusion_live else "offline"
    )
    performance_status = "partial" if postgres_live else "offline"

    optional_probe_specs = {
        "strike_zone": ("Strike Zone Crypto", "Strike Zone Crypto"),
        "agent_harness": ("Agent harnesses", "ChaseOS / local AI runtimes"),
        "chaseos": ("ChaseOS knowledge + Gate", "ChaseOS"),
    }
    optional_states: dict[str, tuple[str, list[str]]] = {}
    for key, _ in optional_probe_specs.items():
        probe = probes.get(key, {})
        if probe.get("configured") and probe.get("ok"):
            optional_states[key] = ("live", ["Configured health probe passed"])
        elif probe.get("configured"):
            optional_states[key] = (
                "offline",
                [f"Configured health probe failed: {probe.get('reason', 'unreachable')}"],
            )
        else:
            optional_states[key] = (
                "contract_only",
                ["Repository contract exists; no runtime endpoint is configured"],
            )

    nodes = [
        _node(
            node_id="hyperliquid",
            label="Hyperliquid public market",
            owner="Hyperliquid",
            tier="A",
            stage="source",
            status="live" if market_live else "offline",
            required_for_tier_a=True,
            authority="authoritative_market",
            summary=(
                "Authoritative perpetual-market source is answering through the market adapter."
                if market_live
                else "No verified Hyperliquid provider response is reaching TradeSync."
            ),
            evidence=[
                f"Provider enabled: {str(hyperliquid_enabled).lower()}",
                f"Status probe: {market_latency:.0f} ms" if market_latency is not None else "Status probe unavailable",
            ],
            missing=[] if market_live else ["Live provider response"],
            impact="Market observation stops when this source is unavailable.",
            recovery=_recovery(
                "restart",
                "Restart the market-data adapter, then inspect provider errors",
                "market-data",
                "docker compose ... up -d --build market-data",
            ),
        ),
        _node(
            node_id="market_data",
            label="Market normalization",
            owner="TradeSync",
            tier="A",
            stage="ingest",
            status="live" if market_live and observation_count else "partial" if market_live else "offline",
            required_for_tier_a=True,
            authority="authoritative_market_derived",
            summary=f"{observation_count}/{catalog_feature_count} catalog inputs are currently exposed for BTC-PERP.",
            evidence=[
                f"Current feature observations: {observation_count}",
                "Mark, funding, OI, volume, and L2 inputs retain explicit provenance",
            ],
            missing=[
                "Direct liquidation flow",
                "Direct CVD",
                "One-hour return derivation",
            ],
            impact="Existing observations continue; missing inputs reduce regime coverage rather than becoming zeroes.",
            recovery=_recovery(
                "inspect",
                "Inspect unavailable feature reasons in Regime Lab",
                "market-data + Regime Lab",
            ),
        ),
        _node(
            node_id="redis",
            label="Redis transport",
            owner="TradeSync",
            tier="A",
            stage="transport",
            status="healthy" if redis_live else "offline",
            required_for_tier_a=True,
            authority="rebuildable_transport",
            summary="Live stream/cache transport is reachable." if redis_live else "Redis transport is unreachable.",
            evidence=[f"PING: {'passed' if redis_live else 'failed'}"],
            missing=[] if redis_live else ["Stream and feature-history transport"],
            impact="Durable reads remain possible, but real-time fan-out and rolling feature history stop.",
            recovery=_recovery(
                "restart",
                "Restart Redis, then replay from durable evidence where supported",
                "redis",
                "docker compose ... up -d redis",
            ),
        ),
        _node(
            node_id="postgres",
            label="PostgreSQL durable truth",
            owner="TradeSync",
            tier="A",
            stage="persistence",
            status="healthy" if postgres_live else "offline",
            required_for_tier_a=True,
            authority="durable_operational_truth",
            summary="Durable state and migrations are queryable." if postgres_live else "Durable TradeSync state is unavailable.",
            evidence=[
                f"Database probe: {'passed' if postgres_live else 'failed'}",
                f"Latest signal: {latest_signal or 'none'}",
                f"Latest opportunity: {latest_opportunity or 'none'}",
            ],
            missing=[] if postgres_live else ["Durable decisions, experiments, journal, and outcomes"],
            impact="Execution and durable decisions fail closed when PostgreSQL is unavailable.",
            recovery=_recovery(
                "restart",
                "Restart PostgreSQL and rerun schema-init",
                "postgres + schema-init",
                "docker compose ... up -d postgres schema-init",
            ),
        ),
        _node(
            node_id="regime_engine",
            label="Regime evidence engine",
            owner="TradeSync",
            tier="A",
            stage="intelligence",
            status=regime_status,
            required_for_tier_a=True,
            authority="deterministic_paper_shadow",
            summary=(
                "The versioned rulebook is evaluating live evidence, but not every block has admitted inputs."
                if regime_status == "partial"
                else "The regime rulebook has no live market evidence."
            ),
            evidence=[
                f"Feature inputs visible: {observation_count}/{catalog_feature_count}",
                "Regime Lab owns normalization, quality, and contribution traces",
            ],
            missing=["Full block coverage", "Direct liquidation evidence", "Champion activation/replay gate"],
            impact="Paper risk remains capped and explanations identify missing blocks.",
            recovery=_recovery(
                "develop",
                "Complete liquidation provenance and fixed-window replay before activation",
                "regime engine",
            ),
        ),
        _node(
            node_id="scorer_fusion",
            label="Scorer + opportunity fusion",
            owner="TradeSync",
            tier="A",
            stage="decision_support",
            status=scorer_status,
            required_for_tier_a=True,
            authority="paper_opportunity",
            summary=(
                "Both scorer and fusion health probes passed."
                if scorer_status == "live"
                else "The bounded runtime is not currently producing a verified end-to-end paper opportunity stream."
            ),
            evidence=[
                f"core-scorer health: {probe_label('core_scorer')}",
                f"fusion-engine health: {probe_label('fusion_engine')}",
                f"Latest recorded signal: {latest_signal or 'none'}",
            ],
            missing=[
                f"{name} endpoint and service"
                if probes.get(key, {}).get("configured") is False
                else name
                for key, name, is_live in (
                    ("core_scorer", "core-scorer", scorer_live),
                    ("fusion_engine", "fusion-engine", fusion_live),
                )
                if not is_live
            ],
            impact="Market and Regime Lab continue, but ranked paper opportunities are not refreshed.",
            recovery=_recovery(
                "repair_then_restart",
                "Reconcile the legacy scorer inputs, then start scorer and fusion",
                "core-scorer + fusion-engine",
                "Set PIPELINE_CORE_SCORER_URL and PIPELINE_FUSION_ENGINE_URL, then docker compose ... up -d --build core-scorer fusion-engine state-api",
            ),
        ),
        _node(
            node_id="performance_journal",
            label="Performance + journal loop",
            owner="TradeSync",
            tier="A",
            stage="learning",
            status=performance_status,
            required_for_tier_a=True,
            authority="measured_outcomes",
            summary="The durable store exists, but the current lean runtime has no complete outcome producer." if postgres_live else "No durable outcome store is reachable.",
            evidence=["PostgreSQL schema is the intended outcome authority", "No current closed-loop performance job is verified"],
            missing=["Fill/outcome reconciliation", "MFE/MAE and slippage jobs", "Regime-fit feedback receipts"],
            impact="Trade ideas cannot yet learn from complete paper outcomes automatically.",
            recovery=_recovery(
                "develop",
                "Implement deterministic paper outcome and performance jobs",
                "performance journal",
            ),
        ),
        _node(
            node_id="tradingview_pine",
            label="TradingView + Pine Script",
            owner="TradingView / operator",
            tier="B",
            stage="advisory_ingress",
            status="partial" if ingest_live else "offline",
            required_for_tier_a=False,
            authority="advisory_signal",
            summary="Webhook contract exists, but no live Pine alert path is verified in the bounded runtime.",
            evidence=[
                "POST /ingest/tv and TradingView scoring rules exist",
                f"ingest-gateway health: {probe_label('ingest_gateway')}",
            ],
            missing=["Verified Pine payload version", "Webhook authentication/configuration", "Fresh alert receipt"],
            impact="Hyperliquid observation and deterministic regime evidence continue without Pine alerts.",
            recovery=_recovery(
                "repair_then_restart",
                "Harden the webhook-only path, configure the Pine alert, then start ingest-gateway",
                "ingest-gateway",
                "Set PIPELINE_INGEST_GATEWAY_URL, then docker compose ... up -d --build ingest-gateway state-api",
            ),
        ),
        _node(
            node_id="strike_zone",
            label="Strike Zone Crypto",
            owner="Strike Zone Crypto",
            tier="B",
            stage="research_candidate",
            status=optional_states["strike_zone"][0],
            required_for_tier_a=False,
            authority="paper_candidate",
            summary="Research and performance evidence may enrich TradeSync, but cannot approve or execute a trade.",
            evidence=optional_states["strike_zone"][1] + ["trade_candidate_v1 receipt adapter is the declared boundary"],
            missing=[] if optional_states["strike_zone"][0] == "live" else ["Configured receipt endpoint", "Schema/digest validation", "Replay-safe cursor"],
            impact="Only new Strike Zone candidate intake is blocked; TradeSync-native analysis continues.",
            recovery=_recovery("implement", "Implement and configure the signed candidate receipt adapter", "Strike Zone connector"),
        ),
        _node(
            node_id="agent_harness",
            label="Agent harnesses",
            owner="ChaseOS / local AI runtimes",
            tier="B",
            stage="advisory_analysis",
            status=optional_states["agent_harness"][0],
            required_for_tier_a=False,
            authority="advisory_only",
            summary="Agent runtimes may explain, compare, and draft proposals; deterministic policy remains authoritative.",
            evidence=optional_states["agent_harness"][1] + ["Hermes/Ollama boundary is documented as advisory"],
            missing=[] if optional_states["agent_harness"][0] == "live" else ["Versioned task/response envelope", "Configured health endpoint", "Evidence writeback receipt"],
            impact="Deterministic scoring and UI continue without model availability.",
            recovery=_recovery("implement", "Define the governed agent envelope before connecting a runtime", "agent-harness adapter"),
        ),
        _node(
            node_id="chaseos",
            label="ChaseOS knowledge + Gate",
            owner="ChaseOS",
            tier="B/C",
            stage="knowledge_and_approval",
            status=optional_states["chaseos"][0],
            required_for_tier_a=False,
            authority="canonical_knowledge_and_approval",
            summary="ChaseOS remains the knowledge and approval authority, never a TradeSync startup dependency.",
            evidence=optional_states["chaseos"][1] + ["knowledge_sync_v1 contract exists"],
            missing=[] if optional_states["chaseos"][0] == "live" else ["Read-only GraphSnapshot adapter", "Gate status adapter", "Configured health endpoint"],
            impact="Knowledge promotion and ChaseOS approvals are blocked; Tier A market work continues.",
            recovery=_recovery("implement", "Connect the read-only knowledge adapter before any Gate integration", "ChaseOS connector"),
        ),
        _node(
            node_id="execution",
            label="Wallet + Hyperliquid execution",
            owner="Isolated signer / Hyperliquid",
            tier="C",
            stage="execution",
            status="locked",
            required_for_tier_a=False,
            authority="approval_gated_execution",
            summary="Execution is deliberately unavailable in the current paper-only runtime.",
            evidence=["execution_authority=false", "exec-hl-svc is outside the bounded runtime"],
            missing=["Isolated wallet", "Single-use ChaseOS approval", "Final risk check", "Reconciliation"],
            impact="No order can be signed or sent; research and paper workflows remain available.",
            recovery=_recovery("approval_required", "Do not restart; complete the governed wallet phase first", "signer + Gate + executor"),
        ),
    ]

    by_id = {node["id"]: node for node in nodes}

    def edge(source: str, target: str, label: str, *, optional: bool = False) -> dict[str, Any]:
        source_state = by_id[source]["status"]
        target_state = by_id[target]["status"]
        if target_state == "locked":
            status = "locked"
        elif source_state in HEALTHY_STATES and target_state in HEALTHY_STATES:
            status = "flowing"
        elif optional and source_state in {"offline", "contract_only", "planned"}:
            status = "not_connected"
        else:
            status = "partial"
        return {"from": source, "to": target, "label": label, "status": status}

    edges = [
        edge("hyperliquid", "market_data", "public market observations"),
        edge("market_data", "redis", "rolling feature history"),
        edge("market_data", "postgres", "durable evidence boundary"),
        edge("redis", "regime_engine", "cadence-governed windows"),
        edge("regime_engine", "scorer_fusion", "quality-weighted evidence"),
        edge("scorer_fusion", "performance_journal", "paper candidates and outcomes"),
        edge("tradingview_pine", "scorer_fusion", "Pine alert receipt", optional=True),
        edge("strike_zone", "scorer_fusion", "validated paper candidate", optional=True),
        edge("agent_harness", "scorer_fusion", "advisory explanation", optional=True),
        edge("chaseos", "agent_harness", "approved knowledge snapshot", optional=True),
        edge("chaseos", "execution", "single-use approval", optional=True),
        edge("scorer_fusion", "execution", "approved order intent", optional=True),
    ]

    tier_a_nodes = [node for node in nodes if node["required_for_tier_a"]]
    ready_count = sum(node["status"] in HEALTHY_STATES for node in tier_a_nodes)
    tier_a_status = "ready" if ready_count == len(tier_a_nodes) else (
        "offline" if ready_count == 0 else "partial"
    )
    connected_optional = sum(
        node["status"] in HEALTHY_STATES
        for node in nodes
        if not node["required_for_tier_a"] and node["tier"] in {"B", "B/C"}
    )

    priority = {"offline": 0, "partial": 1, "contract_only": 2, "locked": 3, "planned": 4}
    recovery_queue = [
        {
            "node_id": node["id"],
            "label": node["label"],
            "status": node["status"],
            "required_for_tier_a": node["required_for_tier_a"],
            "missing": node["missing"],
            "impact": node["impact"],
            "recovery": node["recovery"],
        }
        for node in sorted(
            (node for node in nodes if node["status"] not in HEALTHY_STATES),
            key=lambda item: (
                0 if item["required_for_tier_a"] else 1,
                priority.get(item["status"], 9),
                item["label"],
            ),
        )
    ]

    return {
        "schema_version": "integration_pipeline_status_v1",
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "mode": "paper",
        "execution_authority": False,
        "tier_a": {
            "status": tier_a_status,
            "ready_count": ready_count,
            "total_count": len(tier_a_nodes),
            "principle": "Standalone core continues when optional connectors are unavailable.",
        },
        "federated": {
            "status": "connected" if connected_optional else "not_connected",
            "connected_count": connected_optional,
            "total_count": 4,
        },
        "nodes": nodes,
        "edges": edges,
        "recovery_queue": recovery_queue,
        "capability_gaps": [
            {
                "id": "direct_liquidations",
                "status": "unavailable",
                "blocking": "positioning coverage and liquidation-specific explanations",
                "next_action": "Implement a source-provenance adapter; do not substitute the OI proxy.",
            },
            {
                "id": "price_change_24h",
                "status": "deferred_non_blocking",
                "blocking": "nothing in the current Tier A slice",
                "next_action": "Leave blank until a timestamp-aligned authoritative derivation is intentionally scheduled.",
            },
        ],
    }


def _probe_json_sync(base_url: str, path: str, timeout: float) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        with httpx.Client(timeout=timeout, trust_env=False) as client:
            response = client.get(f"{base_url.rstrip('/')}{path}")
            response.raise_for_status()
        return {
            "ok": True,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "data": response.json(),
        }
    except (httpx.HTTPError, ValueError) as exc:
        return {
            "ok": False,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "reason": str(exc),
            "data": {},
        }


async def _probe_json(base_url: str, path: str, timeout: float) -> dict[str, Any]:
    """Run a bounded probe outside the API event loop.

    Several legacy State API routes still perform comparatively slow work on
    the main worker. A probe must not become a false outage merely because that
    event loop is busy serving the Cockpit.
    """

    return await asyncio.to_thread(_probe_json_sync, base_url, path, timeout)


async def collect_integration_pipeline(
    *,
    pool: Any,
    redis_client: Any,
    market_data_url: str,
    catalog_feature_count: int,
) -> dict[str, Any]:
    """Probe only configured/live runtime surfaces and assemble the contract."""

    service_urls = {
        "market": market_data_url,
        "ingest_gateway": os.getenv(
            "INGEST_GATEWAY_URL", "http://ingest-gateway:8080"
        ).strip(),
        "core_scorer": os.getenv(
            "CORE_SCORER_URL", "http://core-scorer:8000"
        ).strip(),
        "fusion_engine": os.getenv(
            "FUSION_ENGINE_URL", "http://fusion-engine:8002"
        ).strip(),
    }
    optional_urls = {
        "strike_zone": os.getenv("STRIKEZONE_CONNECTOR_URL", "").strip(),
        "agent_harness": os.getenv("AGENT_HARNESS_URL", "").strip(),
        "chaseos": os.getenv("CHASEOS_CONNECTOR_URL", "").strip(),
    }

    probe_timeout = float(os.getenv("INTEGRATION_PROBE_TIMEOUT_SECONDS", "3.0"))
    service_probe_timeout = float(
        os.getenv("INTEGRATION_SERVICE_PROBE_TIMEOUT_SECONDS", "0.75")
    )
    market_tasks: dict[str, Any] = {
        "market_health": _probe_json(service_urls["market"], "/healthz", probe_timeout),
        "market_status": _probe_json(service_urls["market"], "/status", probe_timeout),
        "market_features": _probe_json(
            service_urls["market"],
            "/features/hyperliquid/BTC-PERP",
            probe_timeout,
        ),
    }
    market_keys = list(market_tasks)
    market_results = await asyncio.gather(*market_tasks.values())
    probes = dict(zip(market_keys, market_results))

    # Probe optional and currently unstarted services separately. Failed Docker
    # DNS lookups must not delay or invalidate the authoritative market probes.
    service_tasks: dict[str, Any] = {}
    for key in ("ingest_gateway", "core_scorer", "fusion_engine"):
        url = service_urls[key]
        if url:
            service_tasks[key] = _probe_json(url, "/healthz", service_probe_timeout)
        else:
            probes[key] = {
                "ok": False,
                "configured": False,
                "reason": "not configured in active runtime",
                "data": {},
            }
    for key, url in optional_urls.items():
        if url:
            service_tasks[key] = _probe_json(url, "/healthz", service_probe_timeout)

    if service_tasks:
        service_keys = list(service_tasks)
        service_results = await asyncio.gather(*service_tasks.values())
        probes.update(dict(zip(service_keys, service_results)))
        for key in service_keys:
            probes[key]["configured"] = True

    for key, url in optional_urls.items():
        if key not in probes:
            probes[key] = {"ok": False, "configured": False, "data": {}}
        else:
            probes[key]["configured"] = bool(url)

    postgres_result: dict[str, Any] = {"ok": False}
    if pool:
        try:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    select
                      (select max(created_at) from signals) as latest_signal_ts,
                      (select max(snapshot_ts) from opportunities) as latest_opportunity_ts
                    """
                )
            postgres_result = {
                "ok": True,
                "latest_signal_ts": row["latest_signal_ts"].isoformat()
                if row and row["latest_signal_ts"]
                else None,
                "latest_opportunity_ts": row["latest_opportunity_ts"].isoformat()
                if row and row["latest_opportunity_ts"]
                else None,
            }
        except Exception as exc:  # surfaced as evidence, never endpoint failure
            postgres_result = {"ok": False, "reason": str(exc)}

    redis_result: dict[str, Any] = {"ok": False}
    if redis_client:
        try:
            redis_result = {"ok": bool(await redis_client.ping())}
        except Exception as exc:  # surfaced as evidence, never endpoint failure
            redis_result = {"ok": False, "reason": str(exc)}

    return assemble_pipeline_status(
        probes=probes,
        postgres=postgres_result,
        redis=redis_result,
        catalog_feature_count=catalog_feature_count,
    )
