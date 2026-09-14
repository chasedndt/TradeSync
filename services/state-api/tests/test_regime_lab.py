import json
import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
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
WEIGHTS = {
    "price_volatility": 0.25,
    "liquidity": 0.35,
    "positioning": 0.20,
    "spot_premium": 0.10,
    "macro_flows": 0.10,
}
REQUEST = {
    "name": "Liquidity test",
    "version": "1.0.0-api-test",
    "hypothesis": "Increasing liquidity weight should penalize fragile market evidence.",
    "weights": WEIGHTS,
    "hours": 168,
    "horizon_minutes": 60,
}
REPLAY = {
    "schema_version": "regime_replay_judgement_v1",
    "decisions": {"replayed": 10, "changed": 2, "admissions_gained": 0, "admissions_lost": 2, "direction_flips": 0},
    "outcomes": {"cases_with_outcome": 4},
    "window": {"hours": 168, "horizon_minutes": 60, "symbol": None},
    "execution_authority": False,
}


def _pool(fetchrow_side_effect):
    conn = MagicMock()
    conn.fetchrow = AsyncMock(side_effect=fetchrow_side_effect)
    transaction = MagicMock()
    transaction.__aenter__ = AsyncMock(return_value=None)
    transaction.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=transaction)
    acquire = MagicMock()
    acquire.__aenter__ = AsyncMock(return_value=conn)
    acquire.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acquire)
    return pool, conn


@patch(
    "app.regime_lab_routes._regime_lab_evidence",
    new=AsyncMock(return_value=(FEATURE_RESULTS, SOURCE_STATUS)),
)
def test_overview_carries_no_learning_questions():
    response = client.get("/state/regime-lab/overview")
    assert response.status_code == 200
    body = response.json()
    assert body["execution_authority"] is False
    assert "learning" not in body and "operator_action_required" not in body


def test_the_single_snapshot_evaluate_route_is_gone():
    assert client.post("/state/regime-lab/evaluate", json=REQUEST).status_code in (404, 405)


def test_save_fails_closed_when_postgres_is_unavailable():
    with patch.object(state, "pool", None):
        response = client.post("/state/regime-lab/experiments", json=REQUEST)
    assert response.status_code == 503
    assert "not saved" in response.json()["detail"]


def test_invalid_weight_total_is_rejected_with_the_reason():
    invalid = {**REQUEST, "weights": {name: 0.1 for name in WEIGHTS}}
    with patch.object(state, "pool", None):
        response = client.post("/state/regime-lab/experiments", json=invalid)
    assert response.status_code == 422
    assert "sum" in response.json()["detail"]


def test_a_short_or_blank_hypothesis_is_a_named_422():
    with patch.object(state, "pool", None):
        short = client.post("/state/regime-lab/experiments", json={**REQUEST, "hypothesis": "too short"})
        blank = client.post("/state/regime-lab/experiments", json={**REQUEST, "hypothesis": " " * 25})
    assert short.status_code == 422 and short.json()["detail"][0]["loc"][-1] == "hypothesis"
    assert blank.status_code == 422 and "hypothesis" in blank.json()["detail"]


def test_save_replays_on_the_server_and_stores_hypothesis_weights_and_judgement():
    pool, conn = _pool([{"id": "base-id"}, {"id": "challenger-id"}, {"id": "experiment-id"}])
    with (
        patch.object(state, "pool", pool),
        patch("app.regime_lab_routes.run_replay", new=AsyncMock(return_value=REPLAY)) as replay,
    ):
        response = client.post("/state/regime-lab/experiments", json=REQUEST)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["experiment_id"] == "experiment-id" and body["replay"] == REPLAY
    assert body["status"] == "draft" and body["activation_available"] is False
    judged = replay.call_args.kwargs
    assert judged["hours"] == 168 and judged["horizon_minutes"] == 60 and judged["symbol"] is None
    assert judged["challenger"].weights == WEIGHTS
    challenger_config = json.loads(conn.fetchrow.call_args_list[1].args[8])
    assert challenger_config["blocks"]["liquidity"]["weight"] == 0.35
    assert challenger_config["purpose"] == REQUEST["hypothesis"]
    experiment = conn.fetchrow.call_args_list[2].args
    assert experiment[1] == "Liquidity test" and experiment[5] == REQUEST["hypothesis"]
    assert json.loads(experiment[6])["window_hours"] == 168
    assert json.loads(experiment[7]) == {"replay": REPLAY}


def test_a_reused_version_with_another_configuration_is_a_409():
    class UniqueViolationError(Exception):
        pass

    pool, _ = _pool(UniqueViolationError("duplicate key value"))
    with (
        patch.object(state, "pool", pool),
        patch("app.regime_lab_routes.run_replay", new=AsyncMock(return_value=REPLAY)),
    ):
        response = client.post("/state/regime-lab/experiments", json=REQUEST)
    assert response.status_code == 409
    assert "choose a new version" in response.json()["detail"]


def test_a_slow_replay_during_save_keeps_its_named_error():
    slow = HTTPException(status_code=504, detail="Reading stored decisions did not finish within 45 s")
    with (
        patch.object(state, "pool", MagicMock()),
        patch("app.regime_lab_routes.run_replay", new=AsyncMock(side_effect=slow)),
    ):
        response = client.post("/state/regime-lab/experiments", json=REQUEST)
    assert response.status_code == 504 and "45 s" in response.json()["detail"]


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
