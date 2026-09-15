"""Acceptance phase B: paper positions replayed on the real 1-minute candles of the last hours.

Each replay enters at the first minute after a real opportunity from that time, one per
holding style and a different market each, priced at that candle's open moved by the book
recorded at or before it (aggregated to 3 significant figures, so an upper bound on cost).
It advances on every closed 1-minute candle since, each exit priced from the book recorded at
or before its candle, and settles funding for every hour crossed at the recorded oracle price.
Entry evidence is gathered as of the replay entry: rows stored by then are kept, and answers
fetched now are received after that entry and excluded, which the checks confirm.
"""

import json
import math
import time
import uuid
from bisect import bisect_right

import httpx

from app import editions, paper_entry_sources, paper_funding_store
from tradesync_core import paper_depth as depth
from tradesync_core import paper_entry_evidence as evidence
from tradesync_core import paper_funding as funding
from tradesync_core.managed_paper import advance_on_candle, atr, open_position_on_candle, settle_funding
from tradesync_core.paper_lifecycle_rules import COMMON, RULES

STYLES = ("scalp", "intraday", "swing")
NOTIONAL = 250.0
BAR_S = 60
ATTEMPTS_PER_STYLE = 6


def near(a, b):
    return a is not None and b is not None and math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)


async def candles(market, symbol, interval, start_s, end_s):
    async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
        response = await client.get(f"{market}/candles/hyperliquid/{symbol}",
                                    params={"interval": interval, "start_ms": int(start_s * 1000), "end_ms": int(end_s * 1000)})
        response.raise_for_status()
        return response.json().get("candles") or []


async def recorded_books(conn, symbol, start_s, end_s):
    rows = await conn.fetch("SELECT observed_at, recorded_at, bids, asks FROM public.market_depth_snapshots WHERE symbol=$1 AND n_sig_figs=3 "
                            "AND recorded_at BETWEEN to_timestamp($2) AND to_timestamp($3) ORDER BY recorded_at", symbol, start_s - 600, end_s)
    books = []
    for r in rows:
        book = {"bids": json.loads(r["bids"]), "asks": json.loads(r["asks"])}
        source = depth.snapshot(book, observed_at=r["observed_at"].timestamp(), received_at=r["recorded_at"].timestamp(),
                                source="market_depth_snapshots", precision="aggregated_3_sig_figs")
        books.append((r["recorded_at"].timestamp(), book, source))
    return books


def book_at(books, at):
    index = bisect_right([b[0] for b in books], at) - 1
    return books[index] if index >= 0 else None


async def replay(ctx, opp, style, now):
    rules, symbol, side = RULES[style], opp["symbol"], opp["dir"].lower()
    entry_time = math.ceil(opp["snapshot_ts"].timestamp() / BAR_S) * BAR_S
    base = {"symbol": symbol, "style": style, "side": side, "opportunity": str(opp["id"]), "snapshot_ts": opp["snapshot_ts"].isoformat()}
    bars = [b for b in await candles(ctx.market, symbol, "1m", entry_time, now) if entry_time <= b["time"] and b["time"] + BAR_S <= now]
    books = await recorded_books(ctx.conn, symbol, entry_time, now)
    entry_book = book_at(books, entry_time)
    if not bars or bars[0]["time"] != entry_time or entry_book is None:
        return {**base, "refused": "no 1-minute candle at the entry minute or no book recorded before it"}
    history = await candles(ctx.market, symbol, rules.atr_interval, entry_time - (rules.atr_period + 4) * rules.atr_seconds, entry_time)
    try:
        volatility = atr(history, rules.atr_seconds, entry_time, rules.atr_period)
        # A past entry's funding rows are all received now and excluded, so its planning rate is the declared
        # floor: the gates can be checked before the slower evidence gathering, with the same answer.
        floor = funding.planning_bps_hour({}, COMMON.planning_funding_floor_bps_hour)
        open_position_on_candle(side, style, NOTIONAL, volatility, bars[0], entry_book[1], cost_source=entry_book[2], planning_funding=floor)
        gathered, _ = await paper_entry_sources.gather(ctx.pool, ctx.market, editions.SELF_URL, opp, as_of=entry_time)
        doc = evidence.document(gathered, entry_time, inputs={
            "captured_at": time.time(), "atr": volatility, "entry_cost_book": entry_book[2],
            "replay": "Entered at a closed 1-minute candle's open; costs from the book recorded at or before each candle."})
        planning = funding.planning_from_records(doc["items"]["funding"]["records"], COMMON.planning_funding_floor_bps_hour)
        state = open_position_on_candle(side, style, NOTIONAL, volatility, bars[0], entry_book[1], cost_source=entry_book[2], planning_funding=planning)
    except ValueError as exc:
        return {**base, "refused": str(exc)}
    identity = uuid.uuid4()
    await ctx.conn.execute("INSERT INTO opportunities SELECT * FROM public.opportunities WHERE id=$1 ON CONFLICT DO NOTHING", opp["id"])
    await ctx.conn.execute("INSERT INTO managed_paper_positions (id,opportunity_id,symbol,entry_evidence,evidence_sha256,initial_plan,position_state) "
                           "VALUES($1,$2,$3,$4::jsonb,$5,$6::jsonb,$6::jsonb)", identity, opp["id"], symbol, evidence.canonical_json(doc),
                           evidence.digest(doc), json.dumps(state))
    missing_minutes = 0
    for bar in bars:
        if state["status"] != "open":
            break
        missing_minutes += int((bar["time"] - state["evaluated_through"]) // BAR_S)
        cost = book_at(books, bar["time"])
        state = advance_on_candle(state, bar, BAR_S, cost[1], time.time(), cost_source=cost[2])
    through = state["exit_time"] if state["status"] == "closed" else state["evaluated_through"]
    hours = funding.settlement_hours(state["entry_time"], through)
    rates, received = await paper_funding_store.published(ctx.market, symbol, hours) if hours else ({}, None)
    await paper_funding_store.store(ctx.conn, identity, symbol, state, rates, received, through)
    rows = await paper_funding_store.rows(ctx.conn, identity)
    state = settle_funding(state, rows)
    await ctx.conn.execute("UPDATE managed_paper_positions SET position_state=$2::jsonb WHERE id=$1", identity, json.dumps(state))
    verify(ctx.checks, f"replay {symbol} {style}", doc, state, rows, bars, entry_book, books)
    stored = await ctx.conn.fetchrow("SELECT entry_evidence, evidence_sha256 FROM managed_paper_positions WHERE id=$1", identity)
    ctx.checks(f"replay {symbol} {style}: digest survives the JSONB round trip", evidence.digest(json.loads(stored["entry_evidence"])) == stored["evidence_sha256"])
    return {**base, "entry_time": entry_time, "reference_open": bars[0]["open"], "entry_price": state["entry_price"], "quantity": state["quantity"],
            "entry_cost_bps": state["slippage"]["entry"]["cost_bps"], "entry_book_observed_at": entry_book[2]["observed_at"], "atr": volatility,
            "stop": state["stop"], "target": state["target"], "expiry": state["expiry"], "candles_evaluated": state["candles"],
            "missing_minutes": missing_minutes, "status": state["status"], "exit": state["exit"], "trail": state["trail"],
            "exit_cost_bps": (state["slippage"]["exit"] or {}).get("cost_bps"), "fees": {k: state["fees"][k] for k in ("rate", "entry_usdc", "exit_usdc", "exit_estimate_usdc")},
            "funding": state["funding"], "funding_rows": rows, "gross_pnl_usdc": state["gross_pnl_usdc"], "fees_usdc": state["fees_usdc"],
            "funding_usdc": state["funding_usdc"], "net_estimate_usdc": state["net_estimate_usdc"], "planning_funding": state["planning"]["funding"],
            "evidence": {k: {"status": i["status"], "kept": len(i["records"]), "excluded": i["excluded_count"],
                             "reasons": sorted({e["reason"] for e in i["excluded"]}), "reason": i["reason"]} for k, i in doc["items"].items()}}


def verify(checks, label, doc, state, rows, bars, entry_book, books):
    entry = doc["entry_time"]
    items = doc["items"]
    kept = [r for item in items.values() for r in item["records"]]
    checks(f"{label}: kept evidence observed and received before the replay entry", all(r["observed_at"] <= entry and r["received_at"] <= entry for r in kept))
    # Features come from the latest snapshot (observed now); funding rows were observed before entry but received now.
    fetched_now = [items[k] for k in ("features", "funding") if items[k]["excluded_count"]]
    checks(f"{label}: answers fetched now are excluded from the earlier entry",
           bool(fetched_now) and all(e["reason"] in ("observed after entry", "received after entry") for i in fetched_now for e in i["excluded"])
           and all(e["reason"] == "received after entry" for e in items["funding"]["excluded"]),
           {k: sorted({e["reason"] for e in items[k]["excluded"]}) for k in ("features", "funding")})
    checks(f"{label}: rows stored before the entry are kept", items["open_interest"]["status"] == "present" and items["resting_liquidity"]["status"] == "present")
    buy, sell = ("buy", "sell") if state["side"] == "long" else ("sell", "buy")
    checks(f"{label}: entry fill is the open moved by the recorded book's cost",
           near(state["entry_price"], depth.priced(bars[0]["open"], depth.walk(entry_book[1], buy, notional=NOTIONAL))))
    fees = state["fees"]
    checks(f"{label}: entry fee is the taker rate on the entry fill", near(fees["entry_usdc"], fees["rate"] * state["entry_price"] * state["quantity"]))
    if state["status"] == "closed":
        e = state["exit"]
        bar = next(b for b in bars if b["time"] == e["trigger_observation"]["open_time"])
        cost = book_at(books, bar["time"])
        checks(f"{label}: exit records its rule and the candle that fired it", e["rule"] in ("stop", "trailing_stop", "target", "time_expiry") and e["trigger_observation"]["open"] == bar["open"])
        checks(f"{label}: exit fill is the trigger price moved by the book recorded before that candle",
               near(e["fill_price"], depth.priced(e["trigger_price"], depth.walk(cost[1], sell, quantity=state["quantity"]))))
        checks(f"{label}: a gap fill starts from the open, past the level", not e["gap_fill"] or (e["trigger_price"] == bar["open"] and e["path"] == "open"))
        checks(f"{label}: exit fee is the taker rate on the exit fill", near(fees["exit_usdc"], fees["rate"] * state["exit_price"] * state["quantity"]))
    through = state["exit_time"] if state["status"] == "closed" else state["evaluated_through"]
    hours = [int(r["settled_at"]) for r in rows]
    checks(f"{label}: a funding row or a missing marker for every hour crossed", sorted(hours + state["funding"]["missing_hours"]) == funding.settlement_hours(entry, through))
    sign = 1 if state["side"] == "long" else -1
    checks(f"{label}: each payment is side x quantity x price x rate", all(near(r["payment_usdc"], sign * r["quantity"] * r["price"] * r["funding_rate"]) for r in rows))
    checks(f"{label}: net is gross minus fees minus settled funding", near(state["net_estimate_usdc"], state["gross_pnl_usdc"] - state["fees_usdc"] - state["funding_usdc"])
           and near(state["funding_usdc"], math.fsum(r["payment_usdc"] for r in rows)))


async def run(ctx, hours):
    """One real opportunity per tracked symbol from the start of the window; each tries the styles not yet replayed.

    Styles are tried scalp first, so a symbol admissible for a shorter style is not spent on swing. An
    opportunity backs at most one replay (positions are unique per opportunity).
    """
    now = time.time()
    start = now - hours * 3600
    universe = await editions.tracked_symbols(ctx.market)
    opportunities = await ctx.conn.fetch("SELECT DISTINCT ON (symbol) * FROM public.opportunities WHERE snapshot_ts BETWEEN to_timestamp($1) "
                                         "AND to_timestamp($2) AND lower(dir) IN ('long','short') AND symbol = ANY($3::text[]) "
                                         "ORDER BY symbol, snapshot_ts", start, start + 3600, universe)
    results, covered = [], set()
    for opp in sorted(opportunities, key=lambda row: row["snapshot_ts"]):
        for style in [s for s in STYLES if s not in covered]:
            try:
                outcome = await replay(ctx, dict(opp), style, now)
            except httpx.HTTPError as exc:  # market data unreachable: recorded, never replaced by a guess
                outcome = {"symbol": opp["symbol"], "style": style, "opportunity": str(opp["id"]), "refused": f"market data unavailable: {type(exc).__name__}"}
            results.append(outcome)
            if "refused" not in outcome:
                covered.add(style)
                break
    refusals = {}
    for r in results:
        if "refused" in r:
            refusals.setdefault(r["style"], {}).setdefault(r["refused"], []).append(r["symbol"])
    ctx.checks("replays: at least two holding styles replayed on real candles", len(covered) >= 2, refusals)
    return {"symbols_tried": [row["symbol"] for row in sorted(opportunities, key=lambda row: row["snapshot_ts"])],
            "styles_replayed": sorted(covered), "refusals": refusals, "replays": [r for r in results if "refused" not in r]}
