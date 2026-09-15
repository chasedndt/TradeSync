#!/usr/bin/env python
"""Test the positioning candidates for admission to scoring by the repository's evidence rule.

Declared before any outcome was read: docs/research/2026-09-15_positioning-candidates.md.
Nothing here writes to TradeSync: the export reads Postgres through ``docker exec`` in a
read-only session and the state API with GET requests.

Usage:
    python tools/positioning_candidates.py export --data DIR [--base http://127.0.0.1:8000]
    python tools/positioning_candidates.py assess --data DIR     # writes DIR/assessment.json
    python tools/positioning_candidates.py report --data DIR     # markdown tables on stdout
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "libs" / "tradesync_core"))

from positioning import assess as assessment, report, sources  # noqa: E402
from positioning.candidates import declared_readings  # noqa: E402

CATALOG = ROOT / "config" / "features" / "market-feature-catalog-v1.json"


def skill_gate_costs():
    """The skill gate's own cost figure, imported rather than restated."""
    sys.path.insert(0, str(ROOT / "services" / "state-api"))
    from app.skill_gate import COSTS

    return COSTS


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("export", "assess", "report"))
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--draws", type=int, default=400)
    args = parser.parse_args()

    if args.command == "export":
        print(json.dumps(sources.export(args.data, args.base), indent=2))
        return 0
    if args.command == "assess":
        from tradesync_core.market_features import load_catalog

        catalog = load_catalog(CATALOG)
        readings = declared_readings(catalog.features)
        outcomes, recorded, series, manifest = sources.load(args.data)
        rows, coverage = assessment.build_rows(outcomes, recorded, series, readings, catalog.features)
        result = assessment.assess(rows, readings, coverage, skill_gate_costs(), draws=args.draws)
        result.update({"export": manifest, "catalog_version": catalog.version, "rows": len(rows)})
        (args.data / "assessment.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps({"rows": len(rows), "cells_tested": result["cells_tested"], "decision": result["decision"]}, indent=2))
        return 0
    result = json.loads((args.data / "assessment.json").read_text(encoding="utf-8"))
    print(report.render(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
