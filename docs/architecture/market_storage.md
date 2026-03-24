# Market Data Storage Architecture

> **Purpose**: Document the storage strategy for Phase 3B market data.
> **Last Updated**: 2026-01-21

---

## 1. Design Decision: Redis-First

### Why Redis for V1?

| Factor | Redis | TimescaleDB |
|--------|-------|-------------|
| **Latency** | Sub-ms reads | 5-50ms reads |
| **Setup complexity** | Already deployed | New service needed |
| **Data volume** | Sufficient for 24h rolling | Better for long-term |
| **Cost** | Included | Additional resources |
| **Development speed** | Fast iteration | Slower setup |

### V1 Requirements

- **Real-time access**: Snapshots need sub-100ms read latency
- **Rolling windows**: Only need last 24h-7d for regime detection
- **No historical queries**: No need for long-term analysis yet
- **Simple ops**: Redis already in stack, no new infrastructure

### When to Add TimescaleDB (Phase 3E+)

1. Historical backtesting requires >30 days of tick data
2. Complex SQL queries on market data (TWAP, VWAP, etc.)
3. Need to correlate with trade execution history
4. Storage costs of Redis become prohibitive

---

## 2. Storage Layout

### 2.1 Redis Keys

```
market:snapshot:{venue}:{symbol}     # Hash - latest snapshot
market:ts:{venue}:{symbol}:{metric}  # Sorted Set - timeseries
market:alert:*                       # Stream - alerts (via x:market.alerts)
```

### 2.2 Snapshot Storage (Hash)

```redis
HSET market:snapshot:hyperliquid:BTC-PERP
  data      '{"venue":"hyperliquid","symbol":"BTC-PERP",...}'
  ts        "1737475200000"
  updated_at "1737475200150"

EXPIRE market:snapshot:hyperliquid:BTC-PERP 3600
```

### 2.3 Timeseries Storage (Sorted Set)

```redis
# Score = timestamp, Member = "ts:value"
ZADD market:ts:hyperliquid:BTC-PERP:funding 1737475200000 "1737475200000:0.00003125"
ZADD market:ts:hyperliquid:BTC-PERP:funding 1737475205000 "1737475205000:0.00003150"

# Query last hour
ZRANGEBYSCORE market:ts:hyperliquid:BTC-PERP:funding 1737471600000 1737475200000
```

---

## 3. Data Lifecycle

### 3.1 Snapshots

| Stage | Action | TTL |
|-------|--------|-----|
| Write | On each poll (every 5s) | 1 hour |
| Read | UI requests, regime detection | - |
| Expire | Auto via Redis TTL | 1 hour |

### 3.2 Timeseries

| Stage | Action | Retention |
|-------|--------|-----------|
| Write | On snapshot update | - |
| Prune | ZREMRANGEBYSCORE on write | 24 hours |
| Expire | Auto via Redis TTL | 25 hours |

### 3.3 Alerts

| Stage | Action | Retention |
|-------|--------|-----------|
| Write | On regime change | - |
| Read | /logs page, XREVRANGE | - |
| Trim | XTRIM (optional) | 1000 messages |

---

## 4. MarketStore Interface

```python
class MarketStore(ABC):
    """Abstract interface for market data persistence."""

    @abstractmethod
    async def put_snapshot(self, venue: str, symbol: str, snapshot: MarketSnapshot):
        """Store a snapshot."""
        pass

    @abstractmethod
    async def get_snapshot(self, venue: str, symbol: str) -> Optional[MarketSnapshot]:
        """Get the latest snapshot."""
        pass

    @abstractmethod
    async def get_all_snapshots(self) -> List[MarketSnapshot]:
        """Get all current snapshots."""
        pass

    @abstractmethod
    async def append_timeseries(
        self, venue: str, symbol: str, metric: str, value: float, ts: int
    ):
        """Append to rolling timeseries."""
        pass

    @abstractmethod
    async def get_timeseries(
        self, venue: str, symbol: str, metric: str, start_ts: int, end_ts: int
    ) -> List[Dict]:
        """Query timeseries within range."""
        pass
```

---

## 5. Future: TimescaleDB Integration

### 5.1 Schema Design

```sql
-- Hypertable for snapshots (optional, mainly use Redis)
CREATE TABLE market_snapshots (
    venue TEXT NOT NULL,
    symbol TEXT NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    data JSONB NOT NULL,
    PRIMARY KEY (venue, symbol, ts)
);
SELECT create_hypertable('market_snapshots', 'ts');

-- Hypertable for high-frequency timeseries
CREATE TABLE market_timeseries (
    venue TEXT NOT NULL,
    symbol TEXT NOT NULL,
    metric TEXT NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (venue, symbol, metric, ts)
);
SELECT create_hypertable('market_timeseries', 'ts');

-- Continuous aggregate for hourly stats
CREATE MATERIALIZED VIEW market_hourly
WITH (timescaledb.continuous) AS
SELECT
    venue, symbol, metric,
    time_bucket('1 hour', ts) AS bucket,
    AVG(value) AS avg_value,
    MIN(value) AS min_value,
    MAX(value) AS max_value,
    COUNT(*) AS sample_count
FROM market_timeseries
GROUP BY venue, symbol, metric, bucket;
```

### 5.2 Migration Path

1. **Add TimescaleDB to compose** (Phase 3E)
2. **Implement TimescaleStore** following MarketStore interface
3. **Dual-write**: Write to both Redis (primary) and Timescale (archive)
4. **Gradual cutover**: Use Timescale for historical queries only
5. **Full migration**: Optional, only if Redis costs become issue

### 5.3 Feature Flag

```yaml
# compose.full.yml
market-data:
  environment:
    MARKET_STORE_BACKEND: "redis"  # or "timescale"
    ENABLE_TIMESCALE: "false"
    TIMESCALE_DSN: "postgresql://..."
```

---

## 6. Memory Estimation

### Redis Memory Usage (V1)

| Data Type | Per Symbol | 3 Symbols | 2 Venues |
|-----------|------------|-----------|----------|
| Snapshot | ~2 KB | 6 KB | 12 KB |
| Funding TS (24h @ 5s) | ~500 KB | 1.5 MB | 3 MB |
| OI TS | ~500 KB | 1.5 MB | 3 MB |
| Volume TS | ~500 KB | 1.5 MB | 3 MB |
| **Total** | ~1.5 MB | 4.5 MB | **~9 MB** |

This is well within typical Redis memory limits.

---

## 7. Failure Modes

### 7.1 Redis Unavailable

- **Impact**: Snapshots not stored, UI shows stale data
- **Detection**: Health check fails, poller logs errors
- **Mitigation**: Automatic reconnection, exponential backoff

### 7.2 Data Corruption

- **Impact**: Invalid JSON in snapshot
- **Detection**: Pydantic validation fails on read
- **Mitigation**: Log error, return None, UI shows "Unavailable"

### 7.3 Memory Pressure

- **Impact**: Redis evicts keys
- **Detection**: Missing snapshots, gaps in timeseries
- **Mitigation**: Monitor memory, adjust TTLs, consider Timescale

---

*Last updated: 2026-01-21*
*Phase: 3B — Market Data Expansion*
