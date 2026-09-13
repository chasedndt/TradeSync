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


def _freshness_evidence(readiness: dict[str, Any]) -> str:
    """One line describing whether observations are actually arriving."""
    symbols = readiness.get("symbols") or []
    if not symbols:
        return "Snapshot freshness: not reported by market-data"
    ages = [
        f"{item.get('symbol')} {item.get('age_seconds')}s"
        for item in symbols
        if item.get("age_seconds") is not None
    ]
    state = "fresh" if readiness.get("ready") else readiness.get("reason", "not ready")
    return f"Snapshot freshness ({state}): " + (", ".join(ages) or "no timestamps")

# How recent a stored signal or opportunity must be to count as live evidence.
RECORD_FRESHNESS_SECONDS = int(os.getenv("PIPELINE_RECORD_FRESHNESS_SECONDS", "900"))


def _is_recent(iso_timestamp: str | None) -> bool:
    """Return whether an ISO timestamp is inside the freshness window."""
    if not iso_timestamp:
        return False
    try:
        recorded = datetime.fromisoformat(iso_timestamp)
    except ValueError:
        return False
    if recorded.tzinfo is None:
        recorded = recorded.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - recorded).total_seconds()
    return 0 <= age <= RECORD_FRESHNESS_SECONDS


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
    market_ready = probes.get("market_ready", {})
    # A 503 from /readyz still returns a body, so the report is available even
    # when the probe itself is marked not ok.
    readiness = market_ready.get("data", {}) or {}
    data_flowing = bool(readiness.get("ready"))
    # "live" now requires fresh stored observations, not merely a reachable
    # process. Reporting a frozen poller as live is the exact failure of
    # 2026-09-07.
    market_live = bool(market_health.get("ok") and hyperliquid_enabled and data_flowing)
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

    # A stored record only counts as evidence of a working stage while it is
    # recent. Without this the pipeline would keep reporting a stage as live on
    # the strength of a row written days ago.
    recent_signal = _is_recent(latest_signal)
    recent_opportunity = _is_recent(latest_opportunity)

    # The regime engine is only "live" once its evaluation actually reaches a
    # stored signal. Evaluating in isolation, with nothing consuming the
    # result, is genuinely partial rather than complete.
    regime_status = (
        "live"
        if market_live and observation_count and recent_signal
        else "partial"
        if market_live and observation_count
        else "offline"
    )
    scorer_status = "live" if scorer_live and fusion_live else (
        "partial" if scorer_live or fusion_live else "offline"
    )
    performance_status = (
        "live"
        if postgres_live and (recent_signal or recent_opportunity)
        else "partial"
        if postgres_live
        else "offline"
    )

    # Optional connectors are judged on their own evidence, not on a generic
    # /healthz that some of them do not have (the Hermes API server answers
    # /health; the knowledge connector is a directory of snapshots; Pine
    # alerts are receipts, not a service).
    optional_states: dict[str, tuple[str, list[str]]] = {}

    tv = probes.get("tradingview", {})
    tv_configured = bool(tv.get("configured"))
    tv_recent = tv.get("accepted_24h", 0) or 0
    if tv_configured and tv_recent:
        tv_status = "live"
    elif tv_configured and tv.get("accepted_total"):
        tv_status = "partial"
    elif tv_configured:
        tv_status = "partial"
    else:
        tv_status = "offline"
    tv_evidence = [
        "Receiver: secret " + ("configured" if tv_configured else "NOT configured (endpoint refuses every alert)"),
        f"Public route: {tv.get('public_url') or 'not declared'}",
        f"Accepted alerts: {tv.get('accepted_total', 0)} total, {tv_recent} in the last 24 h"
        + (f"; latest {tv.get('latest_at')} from {tv.get('latest_indicator')}" if tv.get("latest_at") else ""),
    ]
    optional_states["strike_zone"] = (
        "live" if tv_status == "live" else "partial" if tv.get("accepted_total") else "contract_only",
        [f"Strike Zone indicators arrive as TradingView alerts: {tv.get('accepted_total', 0)} received, "
         f"{tv.get('claims_total', 0)} became measured claims"],
    )

    h = probes.get("agent_harness", {})
    if h.get("configured") and h.get("ok"):
        optional_states["agent_harness"] = (
            "live",
            [f"Hermes API server answered at {h.get('url')}: models {', '.join(h.get('models') or []) or 'none listed'}"],
        )
    elif h.get("configured"):
        optional_states["agent_harness"] = ("offline", [f"Hermes API server not answering: {h.get('reason', 'unreachable')}"])
    else:
        optional_states["agent_harness"] = ("contract_only", ["AGENT_HARNESS_URL is unset"])

    g = probes.get("chaseos", {})
    if g.get("configured") and g.get("ok"):
        optional_states["chaseos"] = (
            "live",
            [f"Canonical vault snapshot projected: {g.get('snapshot_id')} ({g.get('nodes')} nodes, {g.get('edges')} edges, built {g.get('created_at')})"],
        )
    elif g.get("configured"):
        optional_states["chaseos"] = ("offline", [f"Snapshot directory configured but nothing projected: {g.get('reason', 'no snapshot')}"])
    else:
        optional_states["chaseos"] = ("contract_only", ["CHASEOS_GRAPH_DIR is unset"])

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
            missing=(
                []
                if market_live
                else ["Fresh stored observations: " + readiness.get("reason", "unknown")]
                if market_health.get("ok") and hyperliquid_enabled
                else ["Live provider response"]
            ),
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
                _freshness_evidence(readiness),
            ],
            missing=(
                # Direct CVD and the one-hour return were implemented on
                # 2026-09-07/08; only liquidation flow remains unavailable.
                ["Direct liquidation flow"]
                if data_flowing
                else [
                    "Direct liquidation flow",
                    f"Fresh stored observations: {readiness.get('reason', 'unknown')}",
                ]
            ),
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
                "The versioned rulebook is evaluating live evidence and feeding stored paper signals."
                if regime_status == "live"
                else "The versioned rulebook is evaluating live evidence, but not every block has admitted inputs."
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
            summary=(
                "Paper signals and opportunities are being recorded; outcome reconciliation is still outstanding."
                if performance_status == "live"
                else "The durable store exists, but the current lean runtime has no complete outcome producer."
                if postgres_live
                else "No durable outcome store is reachable."
            ),
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
            status=tv_status,
            required_for_tier_a=False,
            authority="advisory_signal",
            summary=(
                "Pine alerts are arriving through the authenticated public route and landing in quarantine."
                if tv_status == "live"
                else "The receiver is configured; no alert has arrived in the last 24 hours."
                if tv_status == "partial"
                else "The webhook receiver refuses every alert until TRADINGVIEW_WEBHOOK_SECRET is set."
            ),
            evidence=tv_evidence,
            missing=[] if tv_status == "live" else ["A fresh alert receipt (last 24 h)"] if tv_configured else ["TRADINGVIEW_WEBHOOK_SECRET"],
            impact="Hyperliquid observation and deterministic regime evidence continue without Pine alerts.",
            recovery=_recovery(
                "configure",
                "Point a TradingView alert at the public webhook with the shared secret in its JSON body",
                "TradingView alert + Cloudflare tunnel",
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
            summary=(
                "Pine indicators that submit alerts. Research evidence may enrich "
                "TradeSync, but cannot approve or execute a trade."
            ),
            evidence=optional_states["strike_zone"][1]
            + [
                # Corrected 2026-09-08: the repository holds Pine Script
                # indicators, not a service. There is nothing to probe.
                "Submission source, not a probeable service: Pine indicators "
                "reach TradeSync as TradingView alerts",
                "Quarantine intake is the declared boundary",
            ],
            missing=[]
            if optional_states["strike_zone"][0] == "live"
            else ["A Strike Zone alert in the last 24 h"] if optional_states["strike_zone"][0] == "partial"
            else ["Alerts configured to post to the receiver"],
            impact="Only new Strike Zone alert intake is blocked; TradeSync-native analysis continues.",
            recovery=_recovery(
                "implement",
                "Decide webhook ingress, then point Pine alerts at the receiver",
                "TradingView webhook + quarantine",
            ),
        ),
        _node(
            node_id="agent_harness",
            label="Hermes (advisory harness)",
            owner="ChaseOS Hermes gateway",
            tier="B",
            stage="advisory_analysis",
            status=optional_states["agent_harness"][0],
            required_for_tier_a=False,
            authority="advisory_only",
            summary="Hermes may explain, compare, draft proposals and read posts for claims; deterministic policy remains authoritative.",
            evidence=optional_states["agent_harness"][1]
            + [
                # The envelope, the probe and the receipt all exist now, so the
                # honest evidence line is what is enforced rather than what is
                # documented. The boundary was "documented as advisory" until
                # 2026-09-08; it is now refused in code and proven against a
                # live model that was prompted into claiming approval.
                "Boundary enforced in code: agent_response_v1 refuses score/direction/approval/order fields, nested or embedded in JSON content",
                "Every accepted answer is filed in quarantine; refused escalation attempts are filed too",
            ],
            missing=[]
            if optional_states["agent_harness"][0] == "live"
            else ["The Hermes gateway API server answering at AGENT_HARNESS_URL"],
            impact="Deterministic scoring and UI continue without model availability.",
            recovery=_recovery("restart", "Start the Hermes gateway (its API server platform); the connector probes /v1/models with the Bearer key", "Hermes gateway"),
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
            evidence=optional_states["chaseos"][1]
            + [
                "knowledge_sync_v1 contract exists",
                # Both halves landed 2026-09-08. The honest evidence line is
                # what is enforced, not what remains to be written.
                "Read-only GraphSnapshot adapter and PostgreSQL projection: no write path to the vault, mount is :ro",
                "Gate wired: an approval binds to one candidate and authorises one paper evaluation; single use enforced by a unique constraint",
            ],
            missing=[]
            if optional_states["chaseos"][0] == "live"
            else ["A graph snapshot in the canonical vault's 07_LOGS/Graph-Snapshots and CHASEOS_GRAPH_DIR set"],
            impact="Knowledge promotion and ChaseOS approvals are blocked; Tier A market work continues.",
            recovery=_recovery("configure", "Run the vault's runtime/graph/builder.py to write a fresh snapshot; the connector projects the newest file", "ChaseOS connector"),
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
                "status": "implemented",
                "blocking": "nothing",
                "next_action": "Derived from the venue's own prevDayPx beside the mark in metaAndAssetCtxs; shown as unavailable when the venue omits it.",
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
    optional_urls: dict[str, str] = {}

    probe_timeout = float(os.getenv("INTEGRATION_PROBE_TIMEOUT_SECONDS", "3.0"))
    service_probe_timeout = float(
        os.getenv("INTEGRATION_SERVICE_PROBE_TIMEOUT_SECONDS", "0.75")
    )
    market_tasks: dict[str, Any] = {
        "market_health": _probe_json(service_urls["market"], "/healthz", probe_timeout),
        # Readiness, not just liveness: a reachable service with frozen
        # pollers must not read as live.
        "market_ready": _probe_json(service_urls["market"], "/readyz", probe_timeout),
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

    # The three optional connectors, on their own evidence.
    probes["agent_harness"] = await _harness_probe()
    probes["chaseos"] = await _knowledge_probe(pool)
    probes["tradingview"] = await _tradingview_probe(pool)

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


async def _harness_probe() -> dict[str, Any]:
    """The Hermes API server, through the connector that knows its dialect."""
    from app import agent_connector

    if not agent_connector.configured():
        return {"ok": False, "configured": False}
    result = await agent_connector.probe()
    return {
        "ok": result.get("status") == "live",
        "configured": True,
        "url": result.get("url"),
        "models": result.get("models", []),
        "reason": result.get("detail", ""),
    }


async def _knowledge_probe(pool: Any) -> dict[str, Any]:
    """The projected canonical-vault snapshot, if the connector is configured."""
    from app import graph_projection

    if graph_projection.snapshot_directory() is None:
        return {"ok": False, "configured": False}
    if not pool:
        return {"ok": False, "configured": True, "reason": "database pool not ready"}
    try:
        async with pool.acquire() as conn:
            current = await graph_projection.current_snapshot(conn)
    except Exception as exc:  # evidence, never an endpoint failure
        return {"ok": False, "configured": True, "reason": f"{type(exc).__name__}: {exc}"}
    if not current:
        files = graph_projection.available_snapshots()
        return {"ok": False, "configured": True,
                "reason": f"{len(files)} snapshot file(s) present, none projected yet" if files else "no snapshot files in the directory"}
    return {
        "ok": True, "configured": True,
        "snapshot_id": current.get("snapshot_id"), "nodes": current.get("node_count"), "edges": current.get("edge_count"),
        "created_at": current.get("created_at"),
    }


async def _tradingview_probe(pool: Any) -> dict[str, Any]:
    """Pine alert receipts: the receiver's configuration and what has actually arrived."""
    configured = bool(os.getenv("TRADINGVIEW_WEBHOOK_SECRET", "").strip())
    out: dict[str, Any] = {"ok": False, "configured": configured, "public_url": os.getenv("TRADINGVIEW_PUBLIC_URL", "").strip() or None,
                           "accepted_total": 0, "accepted_24h": 0, "claims_total": 0}
    if not pool:
        return out
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT count(*) FILTER (WHERE accepted) AS total,
                       count(*) FILTER (WHERE accepted AND received_at > now() - interval '24 hours') AS recent,
                       max(received_at) FILTER (WHERE accepted) AS latest,
                       (SELECT payload->>'indicator' FROM quarantine_intake WHERE source = 'tradingview' AND accepted
                          ORDER BY received_at DESC LIMIT 1) AS latest_indicator,
                       (SELECT count(*) FROM evidence_claims WHERE source = 'tradingview') AS claims
                FROM quarantine_intake WHERE source = 'tradingview'
                """
            )
        out.update({
            "accepted_total": int(row["total"] or 0), "accepted_24h": int(row["recent"] or 0),
            "latest_at": row["latest"].isoformat() if row["latest"] else None,
            "latest_indicator": row["latest_indicator"], "claims_total": int(row["claims"] or 0),
        })
        out["ok"] = configured and out["accepted_24h"] > 0
    except Exception as exc:
        out["reason"] = f"{type(exc).__name__}: {exc}"
    return out
