"""Acceptance phase A: a paper position from a real current opportunity, advanced on live books, closed and verified.

Opens through the real route (evidence gathered before the entry quote, a depth-walked fill,
admission under the portfolio lock), advances with the observer's own update every 15 seconds,
closes with the operator close, waits a bounded time for any settled funding hour, then checks
fees, both fills recomputed from the stored books, the funding rows, the entry evidence cut-off,
its digest and the database protections. Numbers are returned for the change record.
"""

import asyncio
import json
import math
import time
import uuid

import asyncpg

from app import paper_funding_store
from tradesync_core import paper_depth as depth
from tradesync_core import paper_entry_evidence as evidence
from tradesync_core import paper_funding as funding

STYLES = ("intraday", "scalp", "swing")
NOTIONAL = 250.0
FUNDING_WAIT_S = 360
CANDIDATE_WAIT_S = 600


def near(a, b):
    return a is not None and b is not None and math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)


async def open_from_candidates(ctx):
    waited = time.time()
    listing = (await ctx.public.get("/state/paper-positions/candidates")).json()
    while not listing.get("candidates") and time.time() - waited < CANDIDATE_WAIT_S:
        await asyncio.sleep(20)  # no fresh opportunity yet: wait for the scorer rather than invent one
        listing = (await ctx.public.get("/state/paper-positions/candidates")).json()
    listing["waited_s"] = time.time() - waited
    refusals = []
    for candidate in listing.get("candidates", []):
        await ctx.conn.execute("INSERT INTO opportunities SELECT * FROM public.opportunities WHERE id=$1 ON CONFLICT DO NOTHING",
                               uuid.UUID(candidate["id"]))
        for style in STYLES:
            response = await ctx.client.post("/state/paper-positions", json={"opportunity_id": candidate["id"], "style": style, "notional": NOTIONAL})
            if response.status_code == 200 and not response.json()["duplicate"]:
                return listing, candidate, style, response.json(), refusals
            refusals.append({"symbol": candidate["symbol"], "style": style, "status": response.status_code, "detail": response.json().get("detail")})
    return listing, None, None, None, refusals


async def observe(ctx, identity, minutes):
    ticks, errors, started, state = 0, [], time.time(), None
    while time.time() - started < minutes * 60:
        await asyncio.sleep(15)
        try:
            state = await ctx.handles.update(identity)
            ticks += 1
            if state["status"] == "closed":
                break
        except Exception as exc:  # a refused quote is recorded; the next tick tries again
            errors.append(f"{type(exc).__name__}: {getattr(exc, 'detail', None) or exc}"[:160])
    return state, ticks, errors


async def close(ctx, identity):
    for _ in range(8):
        response = await ctx.client.post(f"/state/paper-positions/{identity}/close")
        if response.status_code == 200:
            return response.json()
        await asyncio.sleep(3)
    raise AssertionError(f"close refused: {response.text}")


async def refuses(conn, sql, *args):
    try:
        async with conn.transaction():
            await conn.execute(sql, *args)
    except asyncpg.RaiseError:
        return True
    return False


async def run(ctx, minutes):
    checks = ctx.checks
    listing, candidate, style, opened, refusals = await open_from_candidates(ctx)
    result = {"universe": listing.get("universe"), "candidates_offered": len(listing.get("candidates", [])),
              "waited_for_candidates_s": listing.get("waited_s"), "refusals": refusals}
    if not checks("live: a real current opportunity opened a paper position", opened is not None, refusals[-5:]):
        return result
    identity = uuid.UUID(opened["id"])
    state, ticks, errors = await observe(ctx, identity, minutes)
    if state is None or state["status"] == "open":
        state = await close(ctx, identity)
    deadline = time.time() + FUNDING_WAIT_S
    while state["funding"]["status"] == "awaiting_rows" and time.time() < deadline:
        await asyncio.sleep(20)
        state = await ctx.handles.update(identity)
    row = await ctx.conn.fetchrow("SELECT symbol, entry_evidence, evidence_sha256, position_state FROM managed_paper_positions WHERE id=$1", identity)
    doc, final = json.loads(row["entry_evidence"]), json.loads(row["position_state"])
    entry, symbol = doc["entry_time"], row["symbol"]
    kept = [(key, record) for key, item in doc["items"].items() for record in item["records"]]
    checks("live: stored evidence digest matches its fingerprint", evidence.digest(doc) == row["evidence_sha256"])
    checks("live: evidence route verifies the digest", (await ctx.client.get(f"/state/paper-positions/{identity}/evidence")).json()["digest_verified"] is True)
    checks("live: every kept record was observed and received before entry", all(r["observed_at"] <= entry and r["received_at"] <= entry for _, r in kept))
    checks("live: every item is present or missing with a reason", set(doc["items"]) == set(doc["item_order"]) and all(i["status"] == "present" or i["reason"] for i in doc["items"].values()))
    checks("live: every source answered before the entry book was read",
           max(r["received_at"] for _, r in kept if r.get("id") != "entry_book") <= doc["entry_book"]["poll_ts"] / 1000)
    checks("live: entry evidence refuses an update", await refuses(ctx.conn, "UPDATE managed_paper_positions SET entry_evidence = entry_evidence || '{\"late\": true}'::jsonb WHERE id=$1", identity))
    fees, sign = final["fees"], 1 if final["side"] == "long" else -1
    buy, sell = ("buy", "sell") if final["side"] == "long" else ("sell", "buy")
    checks("live: entry fee is the taker rate on the entry fill", near(fees["entry_usdc"], fees["rate"] * final["entry_price"] * final["quantity"]))
    checks("live: exit fee is the taker rate on the exit fill", near(fees["exit_usdc"], fees["rate"] * final["exit_price"] * final["quantity"]))
    checks("live: fee schedule is Hyperliquid's published base rate", fees["schedule"]["taker_fee"] == 0.00045 and "hyperliquid" in fees["schedule"]["source"])
    entry_walk = depth.walk(doc["entry_book"], buy, notional=final["notional"])
    checks("live: entry fill recomputes from the stored entry book", near(entry_walk["price"], final["entry_price"]) and near(entry_walk["total_usdc"], final["slippage"]["entry"]["cost_usdc"]))
    exit_book = json.loads(await ctx.conn.fetchval("SELECT payload FROM managed_paper_events WHERE position_id=$1 AND kind='closed'", identity))["book"]
    exit_walk = depth.walk(exit_book, sell, quantity=final["quantity"])
    checks("live: exit fill recomputes from the stored exit book", near(exit_walk["price"], final["exit_price"]) and near(exit_walk["total_usdc"], final["slippage"]["exit"]["cost_usdc"]))
    rows = await paper_funding_store.rows(ctx.conn, identity)
    hours = [int(r["settled_at"]) for r in rows]
    checks("live: a funding row or a missing marker for every settlement held", sorted(hours + final["funding"]["missing_hours"]) == funding.settlement_hours(final["entry_time"], final["exit_time"]))
    checks("live: each payment is side x quantity x price x rate", all(near(r["payment_usdc"], sign * r["quantity"] * r["price"] * r["funding_rate"]) for r in rows))
    # The nearest recorded minute can change after a row is stored, so check the minute the row names.
    recorded = [await ctx.conn.fetchval("SELECT oracle_price FROM public.market_open_interest WHERE symbol=$1 AND observed_at = to_timestamp($2)",
                                        symbol, r["price_observed_at"]) for r in rows]
    checks("live: funding valued at an oracle price recorded within the settlement window",
           all(near(p, r["price"]) and -300 <= r["price_observed_at"] - r["settled_at"] <= 60 for p, r in zip(recorded, rows)),
           [{"settled_at": r["settled_at"], "price": r["price"], "recorded": p, "price_observed_at": r["price_observed_at"]} for p, r in zip(recorded, rows)])
    checks("live: funding total is the sum of stored rows", near(final["funding_usdc"], math.fsum(r["payment_usdc"] for r in rows)))
    checks("live: net is gross minus fees minus funding", near(final["net_estimate_usdc"], final["gross_pnl_usdc"] - final["fees_usdc"] - final["funding_usdc"]))
    if rows:
        checks("live: stored funding refuses update and delete",
               await refuses(ctx.conn, "UPDATE managed_paper_funding SET payment_usdc=0 WHERE position_id=$1", identity)
               and await refuses(ctx.conn, "DELETE FROM managed_paper_funding WHERE position_id=$1", identity))
    events = [r["kind"] for r in await ctx.conn.fetch("SELECT kind FROM managed_paper_events WHERE position_id=$1 ORDER BY created_at", identity)]
    result.update(
        symbol=symbol, style=style, opportunity={k: candidate[k] for k in ("id", "dir", "timeframe", "snapshot_ts", "age_s")},
        ticks=ticks, tick_errors=errors, events=events, observations=final["observations"], max_quote_gap_s=final["max_observation_gap_s"],
        entry_time=final["entry_time"], entry_price=final["entry_price"], quantity=final["quantity"], stop=final["stop"], target=final["target"],
        expiry=final["expiry"], atr=final["atr"], trail=final["trail"], current_stop=final["current_stop"], planned_risk_usdc=final["planned_risk_usdc"],
        entry_fill={k: final["slippage"]["entry"].get(k) for k in ("touch", "mid", "half_spread_bps", "depth_bps", "total_bps", "cost_usdc", "levels_taken", "snapshot")},
        exit=final["exit"], exit_fill={k: final["slippage"]["exit"].get(k) for k in ("touch", "mid", "half_spread_bps", "depth_bps", "total_bps", "cost_usdc", "levels_taken")},
        fees={k: fees[k] for k in ("rate", "entry_usdc", "exit_usdc")}, fee_schedule=fees["schedule"], funding=final["funding"], funding_rows=rows,
        gross_pnl_usdc=final["gross_pnl_usdc"], fees_usdc=final["fees_usdc"], funding_usdc=final["funding_usdc"], net_estimate_usdc=final["net_estimate_usdc"],
        evidence={"schema": doc["schema_version"], "digest": row["evidence_sha256"], "entry_time": entry, "excluded_count": doc["excluded_count"],
                  "items": {k: {"status": i["status"], "kept": len(i["records"]), "excluded": i["excluded_count"], "newest_age_s": i["newest_age_s"], "reason": i["reason"]}
                            for k, i in doc["items"].items()}})
    return result
