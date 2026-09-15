"""Markdown tables for the research record, rendered from ``assessment.json``."""

from __future__ import annotations

import time
from typing import Any, Mapping

from .candidates import RECORDED_AT_ENTRY

HORIZONS = (15, 60, 240)
REASON_CODES = {
    "too few independent windows": "W",
    "no positive skill": "S",
    "failed hold-out": "H",
    "negative after costs": "C",
    "no observations": "0",
}


def _pct(value: float | None, digits: int = 1) -> str:
    return "—" if value is None else f"{value * 100:.{digits}f}%"


def _fixed(value: float | None, digits: int = 3) -> str:
    return "—" if value is None else f"{value:+.{digits}f}"


def _utc(seconds: int | None) -> str:
    return "—" if seconds is None else time.strftime("%d %b %H:%M", time.gmtime(seconds))


def _cells(reading: Mapping[str, Any], horizon: int) -> tuple[dict | None, dict | None]:
    found = {c["polarity"]: c for c in reading["cells"] if c["horizon_minutes"] == horizon}
    return found.get("as_read"), found.get("inverted")


def _better(*cells: dict | None) -> dict | None:
    present = [c for c in cells if c is not None]
    return max(present, key=lambda c: c["z"] if c["z"] is not None else float("-inf")) if present else None


def coverage_table(result: Mapping[str, Any]) -> str:
    lines = ["| Reading | Entry value from | Entries with a reading | Zero (abstains) | Calls 15m / 60m / 240m | First – last entry (UTC) |",
             "|---|---|---:|---:|---|---|"]
    for r in result["readings"]:
        cov = r["coverage"]
        calls = " / ".join(str((_cells(r, h)[0] or {}).get("measured", 0)) for h in HORIZONS)
        source = "entry record" if r["feature_id"] in RECORDED_AT_ENTRY else "feature store"
        lines.append(f"| `{r['reading_id']}` | {source} | {cov['entries']} | {cov['abstained']} | {calls} "
                     f"| {_utc(cov['first_entry_s'])} – {_utc(cov['last_entry_s'])} |")
    return "\n".join(lines)


def _verdict_text(as_read: dict, inverted: dict) -> str:
    for cell, name in ((as_read, "as read"), (inverted, "inverted")):
        if cell and cell["verdict"] != "not earned":
            return f"**{cell['verdict']}** ({name})"
    best = _better(as_read, inverted)
    return "not earned: " + " ".join(REASON_CODES[x] for x in best["reasons"])


def cells_table(result: Mapping[str, Any]) -> str:
    lines = ["| Reading | h | Calls | Indep. pooled (per symbol) | Hit as read | Up-share | Chance as read | Skill as read / inverted "
             "| z as read / inverted | Holm-positive | Hold-out skill as read / inverted (n) | Net after costs as read / inverted | Verdict |",
             "|---|---:|---:|---|---:|---:|---:|---|---|---|---|---|---|"]
    for r in result["readings"]:
        for h in HORIZONS:
            a, i = _cells(r, h)
            if a is None or not a["measured"]:
                lines.append(f"| `{r['reading_id']}` | {h} | 0 | — | — | — | — | — | — | — | — | — | no calls |")
                continue
            holm = ", ".join(name for name, c in (("as read", a), ("inverted", i)) if c and c["positive_skill"]) or "none"
            lines.append(
                f"| `{r['reading_id']}` | {h} | {a['measured']} | {a['independent_pooled']} ({a['independent_per_symbol']}) "
                f"| {_pct(a['hit_rate'])} | {_pct(a['market_up_rate'])} | {_pct(a['expected_hit_rate'])} "
                f"| {_fixed(a['skill'])} / {_fixed(i['skill'])} | {_fixed(a['z'], 2)} / {_fixed(i['z'], 2)} | {holm} "
                f"| {_fixed(a['holdout_skill'])} / {_fixed(i['holdout_skill'])} ({a['holdout_measured']}) "
                f"| {_fixed(a['mean_net_return_pct'])}% / {_fixed(i['mean_net_return_pct'])}% | {_verdict_text(a, i)} |"
            )
    return "\n".join(lines)


def decision_table(result: Mapping[str, Any]) -> str:
    lines = ["| Candidate | 15m | 60m | 240m | Admitted | Most independent windows in a cell (pooled) | Soonest more days, s = 0.10 / 0.05 |",
             "|---|---|---|---|---|---:|---|"]
    features: list[str] = []
    for r in result["readings"]:
        if r["feature_id"] not in features:
            features.append(r["feature_id"])
    for feature in features:
        readings = [r for r in result["readings"] if r["feature_id"] == feature]
        columns = []
        for h in HORIZONS:
            codes: set[str] = set()
            best_z = None
            for r in readings:
                best = _better(*_cells(r, h))
                if best is None:
                    continue
                codes.update(REASON_CODES[x] for x in best["reasons"])
                if best["z"] is not None:
                    best_z = best["z"] if best_z is None else max(best_z, best["z"])
            columns.append((" ".join(sorted(codes)) or "—") + (f" (best z {best_z:+.2f})" if best_z is not None else ""))
        cells = [c for r in readings for c in r["cells"]]
        admitted = any(c["verdict"] == "admit" for c in cells)
        most = max((c["independent_pooled"] for c in cells), default=0)
        more = []
        for key in ("0.1", "0.05"):
            extra = [(max(0.0, c["days_needed"][key] - c["span_days"]), c["horizon_minutes"]) for c in cells if c["days_needed"].get(key)]
            more.append(f"{min(extra)[0]:.0f} ({min(extra)[1]}m)" if extra else "—")
        lines.append(f"| `{feature}` | {columns[0]} | {columns[1]} | {columns[2]} | {'yes' if admitted else 'no'} | {most} | {more[0]} / {more[1]} |")
    return "\n".join(lines)


def render(result: Mapping[str, Any]) -> str:
    export = result.get("export", {})
    return "\n\n".join([
        f"Export {export.get('exported_at_utc', '—')} (commit `{str(export.get('commit', ''))[:7]}`), catalog {result.get('catalog_version', '—')}: "
        f"{result['opportunities']} opportunities with a measured outcome, {result.get('rows', '—')} reading-outcome rows. "
        f"{result['cells_tested']} of the {result['declared_cells']} declared cells had calls and entered the Holm family; "
        f"first-ranked bar z = {result['holm_first_z']:.2f}; independent windows needed for a true skill of 0.10 / 0.05: "
        f"{result['windows_needed']['0.1']} / {result['windows_needed']['0.05']}. Costs {result['costs']['total_pct']:.2f}% per call.",
        "### Coverage\n\n" + coverage_table(result),
        "### Every cell\n\n" + cells_table(result),
        "### Per candidate\n\nReason codes: W too few independent windows, S no positive skill, H failed hold-out, "
        "C negative after costs, 0 no calls. Shown for the better polarity of each reading.\n\n" + decision_table(result),
    ])
