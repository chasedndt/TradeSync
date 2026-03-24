#!/usr/bin/env python3
"""
TradeSync Regression Gate.
Compares a new report.json against a golden baseline.
"""

import json
import sys
import argparse
from pathlib import Path
from typing import Dict, Any, List


def check_regression(current: Dict[str, Any], golden: Dict[str, Any]) -> List[str]:
    errors = []
    
    cur_s = current["summary"]
    gold_s = golden["summary"]
    
    # 1. Pass Rate (±5% absolute)
    cur_pass = cur_s["risk"]["pass_rate"]
    gold_pass = gold_s["risk"]["pass_rate"]
    if abs(cur_pass - gold_pass) > 5.0:
        errors.append(f"Pass Rate shifted: {gold_pass}% -> {cur_pass}% (limit ±5%)")
    
    # 2. Block Rate (±5% absolute)
    cur_block = cur_s["risk"]["blocked"] / cur_s["risk"]["total"] * 100 if cur_s["risk"]["total"] else 0
    gold_block = gold_s["risk"]["blocked"] / gold_s["risk"]["total"] * 100 if gold_s["risk"]["total"] else 0
    if abs(cur_block - gold_block) > 5.0:
        errors.append(f"Block Rate shifted: {gold_block:.1f}% -> {cur_block:.1f}% (limit ±5%)")

    # 3. Top 3 Block Reasons
    cur_reasons = sorted(cur_s["risk"]["reason_breakdown"].items(), key=lambda x: x[1]["count"], reverse=True)[:3]
    gold_reasons = sorted(gold_s["risk"]["reason_breakdown"].items(), key=lambda x: x[1]["count"], reverse=True)[:3]
    
    cur_top_codes = [r[0] for r in cur_reasons]
    gold_top_codes = [r[0] for r in gold_reasons]
    
    if cur_top_codes != gold_top_codes:
        errors.append(f"Top Block Reasons shifted: {gold_top_codes} -> {cur_top_codes}")

    # 4. Avg Final Score (±10% relative)
    cur_score = cur_s["opportunities"]["score_mean"]
    gold_score = gold_s["opportunities"]["score_mean"]
    if gold_score != 0:
        diff_pct = abs(cur_score - gold_score) / abs(gold_score)
        if diff_pct > 0.10:
            errors.append(f"Avg Final Score shifted: {gold_score:.2f} -> {cur_score:.2f} (diff {diff_pct:.1%}, limit 10%)")
    elif cur_score != 0:
        errors.append(f"Avg Final Score shifted from 0 to {cur_score:.2f}")

    # 5. Avg Microstructure Penalty (±10% relative)
    cur_penalty = cur_s["opportunities"].get("micro_penalty_mean", 0)
    gold_penalty = gold_s["opportunities"].get("micro_penalty_mean", 0)
    if gold_penalty != 0:
        diff_pct = abs(cur_penalty - gold_penalty) / abs(gold_penalty)
        if diff_pct > 0.10:
            errors.append(f"Avg Micro Penalty shifted: {gold_penalty:.2f} -> {cur_penalty:.2f} (diff {diff_pct:.1%}, limit 10%)")
    elif cur_penalty != 0:
        errors.append(f"Avg Micro Penalty shifted from 0 to {cur_penalty:.2f}")

    return errors


def main():
    parser = argparse.ArgumentParser(description="TradeSync Regression Gate")
    parser.add_argument("--current", required=True, help="Path to current report.json")
    parser.add_argument("--golden", required=True, help="Path to golden report.json")
    
    args = parser.parse_args()
    
    current_path = Path(args.current)
    golden_path = Path(args.golden)
    
    if not current_path.exists():
        print(f"Error: Current report {current_path} not found")
        sys.exit(1)
    if not golden_path.exists():
        print(f"Error: Golden report {golden_path} not found")
        sys.exit(1)
        
    with open(current_path) as f:
        current_data = json.load(f)
    with open(golden_path) as f:
        golden_data = json.load(f)
        
    print(f"=== TradeSync Regression Gate ===")
    print(f"Current: {current_path}")
    print(f"Golden:  {golden_path}")
    print()
    
    errors = check_regression(current_data, golden_data)
    
    if errors:
        print("❌ REGRESSION DETECTED:")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)
    else:
        print("✅ PASS: No significant behavior shift detected.")
        sys.exit(0)


if __name__ == "__main__":
    main()
