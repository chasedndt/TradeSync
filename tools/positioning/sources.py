"""Read-only export of the analysis inputs into a directory, and loading them back.

- Measured outcomes and recorded entry readings: SQL piped into ``psql --csv`` inside the
  Postgres container through ``docker exec``, in a read-only session; the credentials never
  leave the container.
- Stored feature series and the tracked symbols: GET requests to the state API.
"""

from __future__ import annotations

import csv
import io
import json
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .candidates import CANDIDATES, PRICE_FEATURE, RECORDED_AT_ENTRY
from .readings import Series, proxy_points

POSTGRES_CONTAINER = "tradesync-full-postgres-1"
SERIES_POINTS = 2000
READ_ONLY = "SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY;\n"

OUTCOMES_SQL = """
SELECT x.opportunity_id, x.symbol, x.horizon_minutes,
       floor(extract(epoch FROM x.opened_at))::bigint AS opened_at_s,
       floor(extract(epoch FROM o.snapshot_ts) * 1000)::bigint AS entry_ms,
       x.forward_return_pct
FROM opportunity_outcomes x
JOIN opportunities o ON o.id = x.opportunity_id
WHERE x.status = 'measured' AND x.forward_return_pct IS NOT NULL
ORDER BY x.opened_at, x.symbol, x.horizon_minutes;
"""

ENTRY_SQL = """
SELECT f.opportunity_id, f.feature_id, f.value,
       floor(extract(epoch FROM f.observed_at) * 1000)::bigint AS observed_at_ms, f.catalog_version
FROM opportunity_entry_features f
WHERE f.value IS NOT NULL AND f.observed_at IS NOT NULL AND f.feature_id = ANY (string_to_array('{features}', ','));
"""


def psql_csv(sql: str) -> list[dict[str, str]]:
    result = subprocess.run(
        ["docker", "exec", "-i", POSTGRES_CONTAINER, "sh", "-c",
         'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" --csv -q -v ON_ERROR_STOP=1'],
        input=READ_ONLY + sql, capture_output=True, text=True, check=True, timeout=600,
    )
    return list(csv.DictReader(io.StringIO(result.stdout)))


def get_json(base: str, path: str, **params: Any) -> Any:
    url = f"{base}{path}" + (f"?{urllib.parse.urlencode(params)}" if params else "")
    with urllib.request.urlopen(url, timeout=180) as response:
        return json.load(response)


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        if rows:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def export(data_dir: Path, base: str) -> dict[str, Any]:
    data_dir.mkdir(parents=True, exist_ok=True)
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    outcomes = psql_csv(OUTCOMES_SQL)
    features = ",".join(sorted(RECORDED_AT_ENTRY | {PRICE_FEATURE}))
    entries = psql_csv(ENTRY_SQL.replace("{features}", features))
    _write_csv(data_dir / "outcomes.csv", outcomes)
    _write_csv(data_dir / "entry_features.csv", entries)
    symbols = [s["symbol"] for s in get_json(base, "/state/market/snapshots")["snapshots"]]
    series_dir = data_dir / "series"
    series_dir.mkdir(exist_ok=True)
    for symbol in symbols:
        body = get_json(base, "/state/regime-lab/feature-history", symbol=symbol,
                        feature_ids=",".join(CANDIDATES), window="7d", points=SERIES_POINTS)
        (series_dir / f"{symbol}.json").write_text(json.dumps(body), encoding="utf-8")
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                            cwd=Path(__file__).resolve().parents[2]).stdout.strip()
    manifest = {"exported_at_utc": started, "outcome_rows": len(outcomes), "entry_readings": len(entries),
                "symbols": symbols, "series_points": SERIES_POINTS, "commit": commit}
    (data_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def load(data_dir: Path) -> tuple[list[dict[str, Any]], dict[str, dict[str, tuple[int, float]]], dict[str, dict[str, Series]], dict[str, Any]]:
    outcomes = [
        {"opportunity_id": r["opportunity_id"], "symbol": r["symbol"], "horizon_minutes": int(r["horizon_minutes"]),
         "opened_at_s": int(r["opened_at_s"]), "entry_ms": int(r["entry_ms"]), "forward_return_pct": float(r["forward_return_pct"])}
        for r in _read_csv(data_dir / "outcomes.csv")
    ]
    recorded: dict[str, dict[str, tuple[int, float]]] = {}
    for r in _read_csv(data_dir / "entry_features.csv"):
        recorded.setdefault(r["opportunity_id"], {})[r["feature_id"]] = (int(r["observed_at_ms"]), float(r["value"]))
    series: dict[str, dict[str, Series]] = {}
    for path in sorted((data_dir / "series").glob("*.json")):
        body = json.loads(path.read_text(encoding="utf-8"))
        series[body["symbol"]] = {f: Series(proxy_points(pairs)) for f, pairs in (body.get("series") or {}).items() if pairs}
    manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
    return outcomes, recorded, series, manifest
