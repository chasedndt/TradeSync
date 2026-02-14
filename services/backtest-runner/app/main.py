"""
Backtest Runner CLI entrypoint.

Usage:
    python -m app.main --dataset data/replay/sample --output data/reports/sample
    python -m app.main --dataset data/replay/sample --realtime --speed 10
"""

import argparse
import json
import sys
from pathlib import Path

from app.replay import ReplayEngine
from app.evaluator import generate_report


def main():
    parser = argparse.ArgumentParser(description="TradeSync Backtest Runner")
    parser.add_argument("--dataset", required=True, help="Path to replay dataset directory")
    parser.add_argument("--output", default=None, help="Output directory for reports (default: data/reports/<dataset_name>)")
    parser.add_argument("--realtime", action="store_true", help="Enable proportional sleep between events")
    parser.add_argument("--speed", type=float, default=1.0, help="Speed multiplier for realtime mode (e.g. 10 = 10x)")

    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        print(f"Error: Dataset path {dataset_path} does not exist", file=sys.stderr)
        sys.exit(1)

    # Load metadata
    metadata_path = dataset_path / "metadata.json"
    metadata = {}
    if metadata_path.exists():
        with open(metadata_path) as f:
            metadata = json.load(f)

    dataset_name = metadata.get("name", dataset_path.name)

    # Determine output directory
    if args.output:
        output_dir = Path(args.output)
    else:
        output_dir = Path("data/reports") / dataset_name
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== TradeSync Backtest Runner ===")
    print(f"Dataset: {dataset_path}")
    print(f"Output:  {output_dir}")
    print(f"Realtime: {args.realtime} (speed={args.speed}x)")
    print()

    # Run replay
    engine = ReplayEngine(
        dataset_path=dataset_path,
        realtime=args.realtime,
        speed=args.speed,
    )

    results = engine.run()

    # Generate reports
    generate_report(results, metadata, output_dir)

    print(f"\nReports written to {output_dir}")
    print(f"  - report.json (full data)")
    print(f"  - report.md (summary)")


if __name__ == "__main__":
    main()
