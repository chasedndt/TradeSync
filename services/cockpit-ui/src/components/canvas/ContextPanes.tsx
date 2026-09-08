import type { IChartApi } from 'lightweight-charts'
import type { ContextSeries, MarketContextResponse } from '../../api/types'
import { ContextPane } from './ContextPane'

interface Props {
  candleTimes: number[]
  context?: MarketContextResponse
  isLoading: boolean
  isError: boolean
  syncWith: IChartApi | null
}

/**
 * Funding and open interest, beneath the price they belong to.
 *
 * The two series do not have the same reach and the panes say so instead of
 * letting a line stop without explanation. Funding is the venue's own hourly
 * record and covers the whole chart. Open interest is our own rolling 24-hour
 * recording, because Hyperliquid publishes only the current value — so on any
 * window wider than a day the pane is honestly short, and the header states
 * the coverage rather than the chart implying a market that stopped existing.
 */
export function ContextPanes({
  candleTimes,
  context,
  isLoading,
  isError,
  syncWith,
}: Props) {
  if (isError) {
    return (
      <p className="tone-bad" style={{ marginTop: 12 }}>
        Context unavailable. Funding and open interest are not drawn from a
        substitute source.
      </p>
    )
  }
  if (isLoading || !context) {
    return (
      <p className="tone-dim" style={{ marginTop: 12 }}>
        Loading funding and open interest…
      </p>
    )
  }

  const summedFunding = context.funding.unit === 'rate_summed_over_bucket'

  return (
    <div style={{ marginTop: 10, display: 'grid', gap: 10 }}>
      <PaneBlock
        title={summedFunding ? 'Funding paid per bucket' : 'Funding rate'}
        detail={
          summedFunding
            ? 'Rates summed across each bucket: the cost actually paid over that period, not one hour picked out of it.'
            : 'Published hourly by the venue, so one point per hour whatever the chart interval.'
        }
        series={context.funding}
        format={formatBps}
      >
        <ContextPane
          candleTimes={candleTimes}
          points={context.funding.series}
          colour="#e3b23c"
          kind="histogram"
          syncWith={syncWith}
          height={82}
          format={formatBps}
        />
      </PaneBlock>

      <PaneBlock
        title="Open interest"
        detail={context.open_interest.limit_note ?? ''}
        series={context.open_interest}
        format={formatUsdCompact}
      >
        <ContextPane
          candleTimes={candleTimes}
          points={context.open_interest.series}
          colour="#5aa9e6"
          kind="line"
          syncWith={syncWith}
          height={96}
          format={formatUsdCompact}
        />
      </PaneBlock>
    </div>
  )
}

function PaneBlock({
  title,
  detail,
  series,
  format,
  children,
}: {
  title: string
  detail: string
  series: ContextSeries
  format: (value: number) => string
  children: React.ReactNode
}) {
  const { coverage } = series
  const latest = series.series.length ? series.series[series.series.length - 1] : null
  const complete = coverage.coverage_pct >= 99

  return (
    <div>
      <div
        style={{
          display: 'flex',
          gap: 12,
          alignItems: 'baseline',
          flexWrap: 'wrap',
          marginBottom: 2,
        }}
      >
        <span className="pipeline-detail-label">{title}</span>
        {latest && <span className="metric-main" style={{ fontSize: 13 }}>{format(latest.value)}</span>}
        <span className={complete ? 'metric-sub' : 'tone-warn'} style={{ fontSize: 11 }}>
          {coverage.covered}/{coverage.candles} buckets · {coverage.coverage_pct}%
        </span>
        <span className="metric-sub" style={{ fontSize: 11, marginLeft: 'auto' }}>
          {series.source}
        </span>
      </div>
      {series.series.length === 0 ? (
        <p className="tone-dim" style={{ fontSize: 12, margin: '4px 0' }}>
          Nothing recorded in this window. The pane stays empty rather than
          drawing a zero line.
        </p>
      ) : (
        children
      )}
      {detail && (
        <p className="market-footnote" style={{ marginTop: 2 }}>
          {detail}
        </p>
      )}
    </div>
  )
}

/** Funding rates are tiny fractions; basis points are the readable unit. */
function formatBps(rate: number): string {
  return `${(rate * 10_000).toFixed(2)} bps`
}

function formatUsdCompact(value: number): string {
  if (Math.abs(value) >= 1e9) return `$${(value / 1e9).toFixed(2)}B`
  if (Math.abs(value) >= 1e6) return `$${(value / 1e6).toFixed(0)}M`
  if (Math.abs(value) >= 1e3) return `$${(value / 1e3).toFixed(0)}K`
  return `$${value.toFixed(0)}`
}
