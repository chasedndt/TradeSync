"""The outlook as written text and as spoken lines, for an edition.

Every sentence comes from the outlook object, which comes from measurements.
"""

from __future__ import annotations

from typing import Any, Mapping


def _when(minutes: int) -> str:
    if minutes < 0:
        return "under way"
    if minutes < 60:
        return f"in {minutes}m"
    if minutes < 48 * 60:
        return f"in {minutes // 60}h {minutes % 60}m"
    return f"in {minutes // 1440}d"


def outlook_text(outlook: Mapping[str, Any] | None) -> list[str]:
    if not outlook:
        return []
    lines = ["## Market outlook", "", outlook["breadth"]["summary"], ""]
    for note in (outlook.get("notes") or [])[1:]:
        lines.append(f"- {note}")
    events = outlook.get("key_events") or []
    if events:
        lines += ["", "### Scheduled this week"]
        for e in events:
            lines.append(f"- **{e['title']}** ({e.get('country') or ''}, {e.get('impact') or ''}) {_when(e['minutes_until'])}")
            for g in (e.get("guidance") or [])[:2]:
                lines.append(f"  - {g}")
            for a in (e.get("articles") or [])[:2]:
                lines.append(f"  - [{a.get('title')}]({a.get('url')}) · {a.get('domain')}")
    lines.append("")
    return lines


def outlook_narration(outlook: Mapping[str, Any] | None) -> list[str]:
    if not outlook:
        return []
    out = [outlook["breadth"]["summary"]]
    for e in (outlook.get("key_events") or [])[:3]:
        if e["minutes_until"] > 48 * 60:
            continue
        out.append(f"{e['title']}, {_when(e['minutes_until'])}.")
        if e.get("guidance"):
            out.append(e["guidance"][0])
    return out
