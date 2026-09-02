import logging
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import DefaultTraceIdFilter, app, state
from app.regime_lab import _repository_config_path


client = TestClient(app)


FEATURE_RESULTS = [
    {
        "feature_id": "hl_spread_bps",
        "block": "liquidity",
        "score": -0.4,
        "data_quality": 0.5,
        "scoring_allowed": True,
    }
]
SOURCE_STATUS = {
    "status": "live",
    "provider": "market-data",
    "venue": "hyperliquid",
    "symbol": "BTC-PERP",
    "observation_count": 1,
}
REQUEST = {
    "name": "Liquidity test",
    "version": "1.0.0-api-test",
    "hypothesis": "Increasing liquidity weight should penalize fragile market evidence.",
    "evaluation_window": "current evidence snapshot",
    "expected_effect": "decrease",
    "weights": {
        "price_volatility": 0.25,
        "liquidity": 0.35,
        "positioning": 0.20,
        "spot_premium": 0.10,
        "macro_flows": 0.10,
    },
    "arithmetic_answer": 1.0,
    "reflection": "Coverage measures available evidence and is not a win probability.",
    "risk_flags": [],
}


@patch(
    "app.main._regime_lab_evidence",
    new=AsyncMock(return_value=(FEATURE_RESULTS, SOURCE_STATUS)),
)
def test_evaluate_is_paper_only_and_persistable_after_learning_gate():
    response = client.post("/state/regime-lab/evaluate", json=REQUEST)
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "paper_shadow"
    assert data["execution_authority"] is False
    assert data["persistable"] is True
    assert data["activation_available"] is False


@patch(
    "app.main._regime_lab_evidence",
    new=AsyncMock(return_value=(FEATURE_RESULTS, SOURCE_STATUS)),
)
def test_save_fails_closed_when_postgres_is_unavailable():
    state.pool = None
    response = client.post("/state/regime-lab/experiments", json=REQUEST)
    assert response.status_code == 503
    assert "not saved" in response.json()["detail"]


def test_invalid_weight_total_is_rejected():
    invalid = {**REQUEST, "weights": {name: 0.1 for name in REQUEST["weights"]}}
    with patch(
        "app.main._regime_lab_evidence",
        new=AsyncMock(return_value=(FEATURE_RESULTS, SOURCE_STATUS)),
    ):
        response = client.post("/state/regime-lab/evaluate", json=invalid)
    assert response.status_code == 422
    assert "sum" in response.json()["detail"]


def test_repository_config_fallback_tolerates_shallow_container_layout():
    assert (
        _repository_config_path(
            "config/features/market-feature-catalog-v1.json",
            Path("/app/app/regime_lab.py"),
        )
        is None
    )


def test_default_trace_filter_supports_dependency_log_records():
    record = logging.LogRecord(
        name="httpx",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="dependency request",
        args=(),
        exc_info=None,
    )
    assert DefaultTraceIdFilter().filter(record) is True
    assert record.trace_id == "-"
