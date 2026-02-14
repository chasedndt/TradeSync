"""
Evaluator: generates report.json (full data) + report.md (summary) from replay results.
"""

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from app.replay import ReplayResults


def generate_report(results: ReplayResults, metadata: Dict[str, Any], output_dir: Path):
    """Generate both JSON and Markdown reports."""
    # Full JSON report
    report_data = {
        "metadata": metadata,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": _build_summary(results),
        "results": results.to_dict(),
    }

    with open(output_dir / "report.json", "w") as f:
        json.dump(report_data, f, indent=2)

    # Markdown summary
    md = _build_markdown(report_data)
    with open(output_dir / "report.md", "w") as f:
        f.write(md)


def _build_summary(results: ReplayResults) -> Dict[str, Any]:
    """Build summary statistics from results."""
    # Signal distribution
    direction_counts = Counter(s.direction for s in results.signals)
    scores = [s.score for s in results.signals]

    signal_stats = {
        "total": len(results.signals),
        "direction_counts": dict(direction_counts),
        "score_min": min(scores) if scores else 0,
        "score_max": max(scores) if scores else 0,
        "score_mean": sum(scores) / len(scores) if scores else 0,
    }

    # Opportunity distribution
    opp_scores = [o.enhanced_score for o in results.opportunities]
    opp_quality = [o.quality for o in results.opportunities]

    opportunity_stats = {
        "total": len(results.opportunities),
        "score_min": min(opp_scores) if opp_scores else 0,
        "score_max": max(opp_scores) if opp_scores else 0,
        "score_mean": sum(opp_scores) / len(opp_scores) if opp_scores else 0,
        "quality_min": min(opp_quality) if opp_quality else 0,
        "quality_max": max(opp_quality) if opp_quality else 0,
        "quality_mean": sum(opp_quality) / len(opp_quality) if opp_quality else 0,
    }

    # Risk verdict breakdown
    reason_counts = Counter(r.reason_code for r in results.risk_verdicts)
    total_verdicts = len(results.risk_verdicts)
    pass_count = sum(1 for r in results.risk_verdicts if r.allowed)
    block_count = total_verdicts - pass_count

    risk_stats = {
        "total": total_verdicts,
        "passed": pass_count,
        "blocked": block_count,
        "pass_rate": round(pass_count / total_verdicts * 100, 1) if total_verdicts else 0,
        "reason_breakdown": {
            code: {"count": count, "pct": round(count / total_verdicts * 100, 1)}
            for code, count in reason_counts.items()
        },
    }

    # Execution risk flags
    all_flags = []
    for o in results.opportunities:
        all_flags.extend(o.execution_risk_flags)
    flag_counts = Counter(all_flags)

    # All warnings
    all_warnings = []
    for o in results.opportunities:
        all_warnings.extend(o.warnings)

    return {
        "events_processed": results.events_processed,
        "symbols_processed": results.symbols_processed,
        "elapsed_seconds": results.elapsed_seconds,
        "signals": signal_stats,
        "opportunities": opportunity_stats,
        "risk": risk_stats,
        "execution_risk_flags": dict(flag_counts),
        "warnings": all_warnings,
    }


def _build_markdown(report: Dict[str, Any]) -> str:
    """Build a human-readable Markdown report."""
    s = report["summary"]
    meta = report.get("metadata", {})

    lines = [
        "# TradeSync Backtest Report",
        "",
        f"**Dataset:** {meta.get('name', 'unknown')}",
        f"**Generated:** {report['generated_at']}",
        f"**Symbols:** {', '.join(s['symbols_processed'])}",
        f"**Events processed:** {s['events_processed']}",
        f"**Elapsed:** {s['elapsed_seconds']}s",
        "",
        "---",
        "",
        "## Signal Distribution",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total Signals | {s['signals']['total']} |",
    ]

    for direction, count in sorted(s["signals"]["direction_counts"].items()):
        lines.append(f"| {direction} | {count} |")

    lines.extend([
        f"| Score Min | {s['signals']['score_min']:.2f} |",
        f"| Score Max | {s['signals']['score_max']:.2f} |",
        f"| Score Mean | {s['signals']['score_mean']:.2f} |",
        "",
        "## Opportunity Distribution",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total | {s['opportunities']['total']} |",
        f"| Enhanced Score Range | [{s['opportunities']['score_min']:.2f}, {s['opportunities']['score_max']:.2f}] |",
        f"| Enhanced Score Mean | {s['opportunities']['score_mean']:.2f} |",
        f"| Quality Range | [{s['opportunities']['quality_min']:.1f}, {s['opportunities']['quality_max']:.1f}] |",
        f"| Quality Mean | {s['opportunities']['quality_mean']:.1f} |",
        "",
        "## Risk Verdict Breakdown",
        "",
        f"| Reason Code | Count | % |",
        f"|-------------|-------|---|",
    ])

    for code, info in sorted(s["risk"]["reason_breakdown"].items()):
        lines.append(f"| {code} | {info['count']} | {info['pct']}% |")

    lines.extend([
        "",
        f"**Pass Rate:** {s['risk']['pass_rate']}% ({s['risk']['passed']} / {s['risk']['total']})",
        "",
    ])

    # Execution risk flags
    if s["execution_risk_flags"]:
        lines.extend([
            "## Execution Risk Flags",
            "",
            "| Flag | Count |",
            "|------|-------|",
        ])
        for flag, count in sorted(s["execution_risk_flags"].items()):
            lines.append(f"| {flag} | {count} |")
        lines.append("")

    # Warnings
    if s["warnings"]:
        lines.extend([
            "## Warnings",
            "",
        ])
        for w in s["warnings"]:
            lines.append(f"- {w}")
        lines.append("")

    return "\n".join(lines)
