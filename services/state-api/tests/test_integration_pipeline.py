from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.integration_pipeline import assemble_pipeline_status
from app.main import app


client = TestClient(app)


def _probes():
    return {
        "market_health": {"ok": True, "data": {"ok": True}, "latency_ms": 8.0},
        "market_status": {
            "ok": True,
            "latency_ms": 12.5,
            "data": {"providers": [{"venue": "hyperliquid", "enabled": True}]},
        },
        "market_features": {"ok": True, "data": {"count": 10}},
        "ingest_gateway": {"ok": False, "configured": False},
        "core_scorer": {"ok": False, "configured": False},
        "fusion_engine": {"ok": False, "configured": False},
        "strike_zone": {"ok": False, "configured": False},
        "agent_harness": {"ok": False, "configured": False},
        "chaseos": {"ok": False, "configured": False},
    }


def test_pipeline_keeps_optional_connectors_out_of_tier_a_readiness():
    status = assemble_pipeline_status(
        probes=_probes(),
        postgres={"ok": True, "latest_signal_ts": None, "latest_opportunity_ts": None},
        redis={"ok": True},
        catalog_feature_count=17,
        generated_at="2026-09-02T12:00:00+00:00",
    )

    assert status["tier_a"] == {
        "status": "partial",
        "ready_count": 4,
        "total_count": 7,
        "principle": "Standalone core continues when optional connectors are unavailable.",
    }
    assert status["federated"]["connected_count"] == 0
    nodes = {node["id"]: node for node in status["nodes"]}
    assert nodes["hyperliquid"]["status"] == "live"
    assert nodes["market_data"]["status"] == "live"
    assert nodes["regime_engine"]["status"] == "partial"
    assert nodes["scorer_fusion"]["status"] == "offline"
    assert "not configured in this runtime" in nodes["scorer_fusion"]["evidence"][0]
    assert nodes["scorer_fusion"]["missing"] == [
        "core-scorer endpoint and service",
        "fusion-engine endpoint and service",
    ]
    assert nodes["chaseos"]["status"] == "contract_only"


def test_24h_price_change_is_explicitly_deferred_and_non_blocking():
    status = assemble_pipeline_status(
        probes=_probes(),
        postgres={"ok": True},
        redis={"ok": True},
        catalog_feature_count=17,
    )
    gaps = {gap["id"]: gap for gap in status["capability_gaps"]}
    assert gaps["price_change_24h"]["status"] == "deferred_non_blocking"
    assert gaps["price_change_24h"]["blocking"] == "nothing in the current Tier A slice"


def test_pipeline_endpoint_returns_the_versioned_contract():
    payload = assemble_pipeline_status(
        probes=_probes(),
        postgres={"ok": True},
        redis={"ok": True},
        catalog_feature_count=17,
    )
    with patch(
        "app.main.collect_integration_pipeline", new=AsyncMock(return_value=payload)
    ):
        response = client.get("/state/integration-pipeline")

    assert response.status_code == 200
    assert response.json()["schema_version"] == "integration_pipeline_status_v1"
    assert response.json()["execution_authority"] is False
