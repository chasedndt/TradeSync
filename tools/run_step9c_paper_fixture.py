#!/usr/bin/env python3
"""Run the Step 9C fixture-only digital twin; never contacts Hyperliquid."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "libs" / "tradesync_core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

from tradesync_core.paper_ledger import PaperLedger, execution_blueprint


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the authority-closed Step 9C fixture simulation")
    parser.add_argument("--candidate", type=Path, default=ROOT / "fixtures" / "step9c" / "candidate.json")
    parser.add_argument("--candles", type=Path, default=ROOT / "fixtures" / "step9c" / "candles.json")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
    candles = json.loads(args.candles.read_text(encoding="utf-8"))
    args.output_dir.mkdir(parents=True, exist_ok=True)

    ledger = PaperLedger(args.output_dir / "paper_ledger.jsonl")
    result = ledger.evaluate(candidate, candles)
    blueprint = execution_blueprint()
    _write_json(args.output_dir / "paper_result.json", result)
    _write_json(args.output_dir / "execution_blueprint.json", blueprint)
    _write_json(
        args.output_dir / "run_metadata.json",
        {
            "schema_version": "step9c_fixture_run_v1",
            "candidate_path": str(args.candidate),
            "candles_path": str(args.candles),
            "result_status": result["status"],
            "authority": {
                "paper_only": True,
                "execution_enabled": False,
                "private_venue_called": False,
                "credential_accessed": False,
                "wallet_action_performed": False,
                "future_live_execution_human_approval_required": True
            }
        },
    )
    print(json.dumps({"ok": True, "status": result["status"], "output_dir": str(args.output_dir)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
