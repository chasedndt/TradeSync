import type { DepthLevel, DepthResponse } from '../../api/types'

interface Props {
  depth?: DepthResponse
  isLoading: boolean
  isError: boolean
}

/**
 * The current order book, beside the chart rather than on it.
 *
 * Depth is not a time series. The book is replaced wholesale on every poll, so
 * there is no honest way to draw it across past candles — an overlay would
 * imply that today's resting size was there yesterday. What can go on the price
 * axis is the walls, and those are drawn dotted so they cannot be mistaken for
 * an operator's own level.
 *
 * Resting size is a description, never a prediction: it can be pulled the
 * instant it is approached.
 */
export function DepthLadder({ depth, isLoading, isError }: Props) {
  if (isError) {
    return (
      <p className="tone-bad">
        Order book unavailable. The venue did not answer and no book is
        reconstructed from snapshots.
      </p>
    )
  }
  if (isLoading || !depth) return <p className="tone-dim">Loading order book…</p>

  const deepest = Math.max(
    depth.bids[depth.bids.length - 1]?.cumulative_usd ?? 0,
    depth.asks[depth.asks.length - 1]?.cumulative_usd ?? 0,
    1,
  )
  const age = Math.max(0, Math.round((Date.now() - depth.poll_ts) / 1000))

  return (
    <div>
      <div style={{ display: 'flex', gap: 18, flexWrap: 'wrap', marginBottom: 10 }}>
        <Figure label="Mid" value={formatPrice(depth.mid_price)} />
        <Figure label="Spread" value={`${depth.spread_bps.toFixed(2)} bps`} />
        <Figure
          label="Imbalance ±1%"
          value={`${depth.imbalance_1pct >= 0 ? '+' : ''}${(depth.imbalance_1pct * 100).toFixed(1)}%`}
          tone={depth.imbalance_1pct >= 0 ? 'good' : 'bad'}
        />
        <Figure label="Book age" value={`${age}s`} tone={age > 30 ? 'bad' : undefined} />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        <Side title="Bids" levels={depth.bids} deepest={deepest} tone="good" />
        <Side title="Asks" levels={depth.asks} deepest={deepest} tone="bad" />
      </div>

      <div style={{ marginTop: 10 }}>
        <span className="pipeline-detail-label">Resting walls</span>
        {depth.walls.length === 0 ? (
          <p className="tone-dim" style={{ fontSize: 12, margin: '4px 0 0' }}>
            None. This book is evenly spread; the largest level is not large
            enough to be worth marking, and nothing is promoted to make the
            panel look busier.
          </p>
        ) : (
          <ul style={{ listStyle: 'none', padding: 0, margin: '4px 0 0' }}>
            {depth.walls.map((wall) => (
              <li
                key={`${wall.side}:${wall.price}`}
                style={{ display: 'flex', gap: 10, fontSize: 12, padding: '2px 0' }}
              >
                <span className={wall.side === 'bid' ? 'tone-good' : 'tone-bad'}>
                  {wall.side.toUpperCase()}
                </span>
                <span className="metric-main" style={{ fontSize: 12 }}>
                  {formatPrice(wall.price)}
                </span>
                <span className="metric-sub">
                  {formatUsd(wall.notional_usd)} ·{' '}
                  {(wall.share_of_side * 100).toFixed(0)}% of that side
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <p className="market-footnote" style={{ marginTop: 10 }}>
        Source: Hyperliquid <code>l2Book</code>, top 10 levels per side &nbsp;•&nbsp;
        cumulative is the cost to sweep to that level &nbsp;•&nbsp; a wall holds
        at least 15% of its own side and can be pulled at any moment
      </p>
    </div>
  )
}

function Side({
  title,
  levels,
  deepest,
  tone,
}: {
  title: string
  levels: DepthLevel[]
  deepest: number
  tone: 'good' | 'bad'
}) {
  const bar = tone === 'good' ? 'rgba(63,178,127,0.22)' : 'rgba(224,87,74,0.22)'
  return (
    <div>
      <span className="pipeline-detail-label">{title}</span>
      <ul style={{ listStyle: 'none', padding: 0, margin: '4px 0 0' }}>
        {levels.map((level) => (
          <li
            key={level.price}
            style={{
              position: 'relative',
              display: 'flex',
              gap: 8,
              fontSize: 11.5,
              padding: '2px 4px',
              fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
            }}
          >
            {/* Width is the cumulative depth, so the bar reads as "how far
                you get before this level", not as this level alone. */}
            <span
              aria-hidden
              style={{
                position: 'absolute',
                inset: 0,
                width: `${(level.cumulative_usd / deepest) * 100}%`,
                background: bar,
                borderRadius: 2,
              }}
            />
            <span className={`tone-${tone}`} style={{ position: 'relative', minWidth: 76 }}>
              {formatPrice(level.price)}
            </span>
            <span className="metric-sub" style={{ position: 'relative', minWidth: 58 }}>
              {level.size.toFixed(3)}
            </span>
            <span className="metric-sub" style={{ position: 'relative', marginLeft: 'auto' }}>
              {formatUsd(level.cumulative_usd)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function Figure({
  label,
  value,
  tone,
}: {
  label: string
  value: string
  tone?: 'good' | 'bad'
}) {
  return (
    <div>
      <span className="metric-sub" style={{ display: 'block' }}>
        {label}
      </span>
      <span className={`metric-main ${tone ? `tone-${tone}` : ''}`} style={{ fontSize: 14 }}>
        {value}
      </span>
    </div>
  )
}

function formatPrice(value: number): string {
  return value.toLocaleString('en-US', {
    minimumFractionDigits: value < 1000 ? 2 : 1,
    maximumFractionDigits: value < 1000 ? 2 : 1,
  })
}

function formatUsd(value: number): string {
  if (value >= 1e6) return `$${(value / 1e6).toFixed(2)}M`
  if (value >= 1e3) return `$${(value / 1e3).toFixed(0)}K`
  return `$${value.toFixed(0)}`
}
