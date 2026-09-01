import json
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MARKET_DATA_ROOT = REPO_ROOT / "services" / "market-data"
sys.path.insert(0, str(MARKET_DATA_ROOT))

from app.models import (  # noqa: E402
    FundingData,
    FundingHorizons,
    FundingSource,
    MetricAvailability,
    MetricStatus,
    MarketSnapshot,
    OpenInterestData,
    VolumeData,
)
from app.processors.snapshotter import MarketSnapshotter  # noqa: E402


class MarketDataMathTests(unittest.TestCase):
    def test_metric_status_includes_derived(self):
        self.assertEqual(MetricStatus.DERIVED.value, "DERIVED")

    def test_hourly_funding_average_annualizes_with_24_hours_and_365_days(self):
        snapshotter = MarketSnapshotter()
        now = 2_000_000_000
        hourly_rate = 0.0001
        funding, metrics, _ = snapshotter._build_funding(
            [
                {
                    "ts": now - 1000,
                    "status": "REAL",
                    "source": {
                        "provider": "hyperliquid",
                        "endpoint": "fundingHistory",
                    },
                    "value": {"rate": hourly_rate},
                }
            ],
            now,
        )
        self.assertAlmostEqual(funding.horizons.h24, hourly_rate)
        self.assertAlmostEqual(
            funding.annualized_24h, hourly_rate * 24 * 365
        )
        self.assertEqual(metrics[0].status, MetricStatus.REAL)

    def test_regime_confidence_requires_funding_oi_and_volume_coverage(self):
        snapshotter = MarketSnapshotter()
        funding = FundingData(
            horizons=FundingHorizons(),
            source=FundingSource(
                provider="hyperliquid", endpoint="fundingHistory", raw_rate=0
            ),
        )
        only_funding = snapshotter._compute_regimes(
            funding,
            None,
            None,
            [
                MetricAvailability(
                    metric="funding", status=MetricStatus.REAL
                )
            ],
        )
        self.assertEqual(only_funding.confidence, "low")
        self.assertIn("oi, volume", only_funding.confidence_note)

        funding_and_oi = snapshotter._compute_regimes(
            funding,
            OpenInterestData(),
            None,
            [
                MetricAvailability(metric="funding", status=MetricStatus.REAL),
                MetricAvailability(metric="oi", status=MetricStatus.REAL),
            ],
        )
        self.assertEqual(funding_and_oi.confidence, "medium")
        self.assertIn("volume", funding_and_oi.confidence_note)

        complete = snapshotter._compute_regimes(
            funding,
            OpenInterestData(),
            VolumeData(),
            [
                MetricAvailability(metric="funding", status=MetricStatus.REAL),
                MetricAvailability(metric="oi", status=MetricStatus.REAL),
                MetricAvailability(metric="volume", status=MetricStatus.REAL),
            ],
        )
        self.assertEqual(complete.confidence, "high")
        self.assertIsNone(complete.confidence_note)

    def test_missing_oi_cannot_create_choppy_condition_from_defaults(self):
        snapshotter = MarketSnapshotter()
        low_volume = VolumeData(regime="low")
        result = snapshotter._compute_regimes(
            None,
            None,
            low_volume,
            [MetricAvailability(metric="volume", status=MetricStatus.REAL)],
        )
        self.assertEqual(result.market_condition.value, "unknown")

    def test_proxy_required_input_cannot_create_market_condition(self):
        snapshotter = MarketSnapshotter()
        funding = FundingData(
            horizons=FundingHorizons(),
            source=FundingSource(
                provider="hyperliquid", endpoint="fundingHistory", raw_rate=0
            ),
        )
        result = snapshotter._compute_regimes(
            funding,
            OpenInterestData(),
            VolumeData(regime="low"),
            [
                MetricAvailability(metric="funding", status=MetricStatus.REAL),
                MetricAvailability(metric="oi", status=MetricStatus.PROXY),
                MetricAvailability(metric="volume", status=MetricStatus.REAL),
            ],
        )
        self.assertEqual(result.market_condition.value, "unknown")
        self.assertEqual(result.confidence, "medium")
        self.assertIn("Proxy inputs: oi", result.confidence_note)

    def test_phase3c_sample_does_not_claim_direct_cvd_or_liquidation_side(self):
        sample_path = REPO_ROOT / "docs" / "samples" / "phase3C" / "market_snapshot.json"
        sample = json.loads(sample_path.read_text(encoding="utf-8"))
        snapshot = MarketSnapshot.model_validate(sample)
        status_by_metric = {
            metric.metric: metric.status for metric in snapshot.available_metrics
        }
        self.assertEqual(status_by_metric["microstructure"], MetricStatus.DERIVED)
        self.assertIsNone(snapshot.volume.cvd)
        self.assertTrue(
            all(
                window.dominant_side == "unavailable"
                for window in snapshot.liquidations.horizons.values()
            )
        )


if __name__ == "__main__":
    unittest.main()
