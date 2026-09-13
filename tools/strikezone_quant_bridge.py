"""Bridge the StrikeZone quant lab into TradeSync: forward-test ledger, outcomes, scorecards, health, charts.

The lab runs in the Hermes fleet in WSL and writes plain files under
``runtime/strikezone/quant_eval``. Docker Desktop cannot mount the distro
here, so this runs on the Windows host (Task Scheduler, pythonw, every five
minutes). Each pass:

- posts the lines appended to ``signals.ndjson`` and ``outcomes.ndjson``
  since the byte offset it last stored. Both files are append-only; a file
  shorter than its cursor was replaced and is read again from the start, and
  storage is idempotent, so a repeat is harmless;
- posts the scorecards, integrity health, methodology, cost assumptions and
  the fleet health state whenever a file's modification time changes;
- copies the charts of the newest trade calls and outcomes to a host folder
  the state API mounts read-only.

Read-only against the lab: never writes into the WSL tree, never posts to
Discord, never runs a job. A cursor advances only after the state API stored
the rows.

Usage (from the repo root, with the project venv):
    python tools/strikezone_quant_bridge.py [--once] [--dry-run] [--interval 300]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Under pythonw.exe (no console window) there is no stdout; log to a file instead.
if sys.stdout is None or sys.stderr is None:
    _log = Path(os.getenv("TRADESYNC_LOG_DIR", r"E:\Projects\TradeSync\dashboard-runtime\logs")) / "strikezone_quant_bridge.log"
    _log.parent.mkdir(parents=True, exist_ok=True)
    sys.stdout = sys.stderr = open(_log, "a", encoding="utf-8", buffering=1)

import httpx  # noqa: E402

HERMES_HOME = Path(os.getenv("HERMES_HOME_WINDOWS", r"\\wsl.localhost\Ubuntu\home\chaseos\runtimes\hermes-home"))
LAB = HERMES_HOME / "runtime" / "strikezone" / "quant_eval"
LEDGERS = {"signals": LAB / "signals.ndjson", "outcomes": LAB / "outcomes.ndjson"}
DOCUMENTS = {
    "scorecards": LAB / "latest_scorecards.json",
    "health": LAB / "health_report.json",
    "methodology": LAB / "methodology_state.json",
    "assumptions": LAB / "assumptions.json",
    "fleet_health": HERMES_HOME / "runtime" / "cron_fleet_health_state.json",
}
CHARTS_OUT = Path(os.getenv("STRIKEZONE_CHARTS_HOST_DIR", r"E:\Projects\TradeSync\dashboard-runtime\strikezone-charts"))
STATE_FILE = Path(os.getenv("STRIKEZONE_BRIDGE_STATE", r"E:\Projects\TradeSync\dashboard-runtime\strikezone-bridge-state.json"))
STATE_API = os.getenv("STATE_API_URL", "http://localhost:8000").rstrip("/")
BATCH = 500
RECENT_IDS = 200
MAX_CHART_COPIES = 60
MAX_MISSING_REMEMBERED = 400
DAILY_RESULTS_KEPT = 30


def load_state() -> dict:
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(tmp, STATE_FILE)


def read_appended(path: Path, offset: int) -> tuple[list[str], int]:
    """Complete lines appended since ``offset``, and the offset just past the last complete line."""
    size = path.stat().st_size
    if size < offset:
        offset = 0
    if size == offset:
        return [], offset
    with path.open("rb") as handle:
        handle.seek(offset)
        data = handle.read(size - offset)
    end = data.rfind(b"\n")
    if end < 0:
        return [], offset
    lines = [line for line in data[: end + 1].decode("utf-8", "replace").splitlines() if line.strip()]
    return lines, offset + end + 1


def parse_lines(lines: list[str]) -> list[dict]:
    rows = []
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def trim_document(kind: str, payload: dict) -> dict:
    """Drop what the dashboard never reads: superseded methodologies, old daily rows, Discord receipts."""
    if kind == "scorecards":
        payload = {k: v for k, v in payload.items() if k != "historical_scorecards"}
        cards = []
        for card in payload.get("scorecards") or []:
            if isinstance(card, dict) and isinstance(card.get("daily_results"), list):
                card = {**card, "daily_results": card["daily_results"][-DAILY_RESULTS_KEPT:]}
            cards.append(card)
        payload["scorecards"] = cards
    elif kind == "fleet_health":
        payload = {k: v for k, v in payload.items() if k not in ("last_receipts", "repair_attempts")}
    return payload


def remember(state: dict, key: str, ids: list[str]) -> None:
    merged = list(dict.fromkeys([*state.get(key, []), *ids]))
    state[key] = merged[-RECENT_IDS:]


def copy_charts(state: dict) -> int:
    """Copy the newest charts not yet on the host, newest first, a bounded number per pass."""
    copied = 0
    missing = set(state.get("missing_charts", []))
    for kind, key in (("signals", "recent_trade_signal_ids"), ("outcomes", "recent_outcome_ids")):
        dest = CHARTS_OUT / kind
        dest.mkdir(parents=True, exist_ok=True)
        for ident in reversed(state.get(key, [])):
            if copied >= MAX_CHART_COPIES:
                break
            target = dest / f"{ident}.png"
            if target.exists() or ident in missing:
                continue
            part = target.with_suffix(".part")
            try:
                shutil.copyfile(LAB / "charts" / kind / f"{ident}.png", part)
                os.replace(part, target)
                copied += 1
            except FileNotFoundError:
                missing.add(ident)  # the lab skips a chart whose render failed
            except OSError as exc:
                print(f"[QuantBridge] chart {ident} not copied ({type(exc).__name__})")
    state["missing_charts"] = sorted(missing)[-MAX_MISSING_REMEMBERED:]
    return copied


def post(client: httpx.Client, body: dict, dry_run: bool) -> None:
    if dry_run:
        return
    response = client.post(f"{STATE_API}/state/strikezone/ingest", json=body)
    response.raise_for_status()


def run_pass(dry_run: bool = False) -> str:
    state = load_state()
    cursors = state.setdefault("cursors", {})
    mtimes = state.setdefault("mtimes", {})
    parts = []
    with httpx.Client(timeout=120.0, trust_env=False) as client:
        for kind, path in LEDGERS.items():
            lines, next_offset = read_appended(path, int(cursors.get(kind, 0)))
            rows = parse_lines(lines)
            for start in range(0, len(rows), BATCH):
                post(client, {kind: rows[start:start + BATCH]}, dry_run)
            if kind == "signals":
                remember(state, "recent_trade_signal_ids",
                         [str(r["signal_id"]) for r in rows if r.get("direction") in ("long", "short") and r.get("signal_id")])
            else:
                remember(state, "recent_outcome_ids", [str(r["outcome_id"]) for r in rows if r.get("outcome_id")])
            parts.append(f"{kind} +{len(rows)}")
            if not dry_run:
                cursors[kind] = next_offset
                save_state(state)
        documents, changed = {}, {}
        for kind, path in DOCUMENTS.items():
            try:
                mtime = path.stat().st_mtime
                if mtimes.get(kind) == mtime:
                    continue
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue  # missing, or caught mid-rewrite; the next pass reads it
            if isinstance(payload, dict):
                updated = datetime.fromtimestamp(mtime, timezone.utc).isoformat()
                documents[kind] = {"payload": trim_document(kind, payload), "source_updated_at": updated}
                changed[kind] = mtime
        if documents:
            post(client, {"documents": documents}, dry_run)
        parts.append(f"documents {','.join(sorted(documents)) or 'unchanged'}")
    if not dry_run:
        mtimes.update(changed)
        parts.append(f"charts +{copy_charts(state)}")
        save_state(state)
    return " | ".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--interval", type=int, default=300)
    args = parser.parse_args()
    if args.once or args.dry_run:
        print(f"[QuantBridge] {datetime.now(timezone.utc).isoformat(timespec='seconds')} {run_pass(dry_run=args.dry_run)}")
        return 0
    while True:
        try:
            print(f"[QuantBridge] {datetime.now(timezone.utc).isoformat(timespec='seconds')} {run_pass()}")
        except Exception as exc:  # keep the loop alive; the next pass retries from the stored cursors
            print(f"[QuantBridge] pass failed: {type(exc).__name__}")
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
