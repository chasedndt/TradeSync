# TradeSync Master Guide

## 🚀 Core Commands
- `docker compose -f ops/compose.full.yml up -d` - **Start** full trade stack
- `docker compose -f ops/compose.full.yml down` - **Stop** all services
- `docker compose -f ops/compose.full.yml logs -f <service>` - **Live Logs** (e.g., `qdrant`, `ingest-gateway`)
- `docker compose -f ops/compose.full.yml exec postgres psql -U tradesync -d tradesync` - **DB Access**

## 🧩 Service Logs Reference
Use these names with the logs command:
- `ingest-gateway`: Market data polling
- `core-scorer`: Technical bias & confidence
- `fusion-engine`: Confluence scoring
- `state-api`: REST snapshots & UI data
- `exec-hl-svc`: Hyperliquid order execution
- `exec-drift-svc`: Drift order execution
- `postgres`, `redis`, `qdrant`: Persistent & memory storage

## 📊 Ultimate Trading Journal Audit
Run this to see the **Full Thesis** including Symbol, Timestamp, Side, Leverage, Decision Logic, and Status:
```sql
SELECT 
    e.id as order_id, 
    o.symbol, 
    e.created_at as timestamp,
    e.request->>'side' as side, 
    e.status, -- Shows 'placed', 'completed', 'cancelled', or 'failed'
    d.risk->>'leverage' as leverage, 
    s.confidence as conviction, 
    s.notes as thesis, 
    o.quality as market_score,
    o.confluence->'indicators' as indicators, 
    d.risk->'stop_loss' as sl, 
    d.risk->'take_profit' as tp
FROM exec_orders e
JOIN decisions d ON e.decision_id = d.id
JOIN opportunities o ON d.opportunity_id = o.id
JOIN signals s ON o.signal_id = s.id
ORDER BY e.created_at DESC;
```

## 🏗️ Project Architecture
(Services communicate via Redis streams and persist to Postgres/Qdrant)
- **Status Meanings**:
  - `placed`: Order sent to venue, awaiting fill.
  - `completed`: Order filled and confirmed on-chain.
  - `cancelled`: Order invalidated by market structure breaking or manual stop.
  - `failed`: Technical error (e.g., API timeout or account balance).

## 🗃️ Database Schema Map
- `signals`: The **Thesis** layer (Agent name, confidence, features, manual notes).
- `opportunities`: The **Score** layer (Market quality, bias, confluence indicators).
- `decisions`: The **Risk** layer (Stops, TPs, risk-adjusted leverage/sizing).
- `exec_orders`: The **Venue** layer (Full raw logs and txid).

## 🛠️ Development Style
- **Python**: FastAPI/Pydantic
- **Messaging**: Redis streams
- **Path**: Use `C:\TradeSync` for stable AI/CLI operations.
