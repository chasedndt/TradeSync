import { useMemo, useState } from 'react'
import { useLiquidationMap, useWindowCandles } from '../../api/hooks/useLiquidity'
import type { Cluster, LiquidationMap as MapData, MapWindow } from '../../api/liquidityTypes'
import { price } from '../ledger/format'
import { HeatmapChart } from './heatmap/HeatmapChart'
import type { HeatLayer } from './heatmap/HeatmapPrimitive'
import { gradient, intensity, liquidationColour } from './heatmap/palette'
import { usdCompact, when } from './marketFormat'
import styles from './LiquidityPanels.module.css'

const WINDOWS: { key: MapWindow; interval: string; limit: number }[] = [
  { key: '24h', interval: '5m', limit: 288 },
  { key: '3d', interval: '15m', limit: 288 },
  { key: '7d', interval: '1h', limit: 168 },
  { key: '30d', interval: '4h', limit: 180 },
]

/** Geometric bins: each band runs halfway (in log terms) to its neighbours. */
function edges(centres: number[]): [number, number][] {
  return centres.map((c, i) => {
    const lower = i > 0 ? Math.sqrt(centres[i - 1] * c) : c * c / Math.sqrt(c * (centres[i + 1] ?? c))
    const upper = i < centres.length - 1 ? Math.sqrt(c * centres[i + 1]) : c * c / Math.sqrt(centres[i - 1] * c)
    return [lower, upper]
  })
}

function toLayer(data: MapData): HeatLayer {
  const totals = data.cells.map(([, , long, short]) => long + short).sort((a, b) => a - b)
  const reference = totals[Math.floor(totals.length * 0.97)] ?? data.max_usd
  return {
    times: data.times,
    bucketSeconds: data.bucket_seconds,
    priceEdges: edges(data.prices),
    cells: data.cells.map(([t, p, long, short]) => ({ t, p, intensity: intensity(long + short, reference) })),
    colour: liquidationColour,
  }
}

function ClusterList({ title, clusters }: { title: string; clusters: Cluster[] }) {
  return (
    <>
      <dt>{title}</dt>
      <dd>{clusters.length ? clusters.map((c) => `${price(c.price)} (${c.distance_pct > 0 ? '+' : ''}${c.distance_pct.toFixed(1)}%) ${usdCompact(c.usd)}`).join(' · ') : 'none'}</dd>
    </>
  )
}

/**
 * Estimated liquidation levels, Coinglass-style: where leveraged positions opened
 * as open interest rose would be forced out, cleared once price trades through
 * them. Bright bands are clusters price may be drawn to; an estimate, not orders.
 */
export function LiquidationMap({ symbol }: { symbol: string }) {
  const [window, setWindow] = useState<MapWindow>('7d')
  const spec = WINDOWS.find((w) => w.key === window) ?? WINDOWS[2]
  const map = useLiquidationMap(symbol, window)
  const candles = useWindowCandles(symbol, spec.interval, spec.limit)
  const data = map.data?.window === window && map.data.symbol === symbol ? map.data : undefined
  const layer = useMemo(() => (data ? toLayer(data) : null), [data])
  const levels = useMemo(() => [
    ...(data?.clusters.above[0] ? [{ price: data.clusters.above[0].price, colour: '#ffbe28', title: 'short liq cluster' }] : []),
    ...(data?.clusters.below[0] ? [{ price: data.clusters.below[0].price, colour: '#ffbe28', title: 'long liq cluster' }] : []),
  ], [data])
  const leverage = data ? Object.entries(data.assumptions.leverage).map(([lev, share]) => `${lev}x ${Math.round(share * 100)}%`).join(', ') : ''

  return (
    <section className={`panel ${styles.panel}`} aria-labelledby="liquidation-map-title">
      <header className={styles.head}>
        <div>
          <h3 id="liquidation-map-title">Liquidation heatmap (estimated)</h3>
          <p>Where leveraged positions would be forced out, estimated from open-interest changes at Hyperliquid prices.</p>
        </div>
        <div className={styles.chips} role="group" aria-label="Window">
          {WINDOWS.map((w) => (
            <button key={w.key} type="button" className={w.key === window ? 'chip chip--active' : 'chip'} aria-pressed={w.key === window} onClick={() => setWindow(w.key)}>{w.key}</button>
          ))}
        </div>
      </header>
      <div className={styles.body}>
        <div className={styles.chartCol}>
          {map.isError && <p className={styles.warn}>Liquidation map unavailable: {(map.error as Error).message}</p>}
          <HeatmapChart candles={candles.data ?? []} layer={layer} intraday={spec.interval !== '1d'} levels={levels} />
          <div className={styles.legend}>
            <span>fewer</span><i style={{ background: gradient(liquidationColour) }} /><span>more estimated liquidations at a price</span>
          </div>
        </div>
        <aside className={styles.side}>
          <h4>Largest clusters</h4>
          {data ? (
            <dl>
              <ClusterList title="Above price (shorts)" clusters={data.clusters.above} />
              <ClusterList title="Below price (longs)" clusters={data.clusters.below} />
              <dt>Balance within 3%</dt>
              <dd>{data.skew_3pct == null ? 'no levels within 3%' : `${data.skew_3pct > 0 ? '+' : ''}${data.skew_3pct.toFixed(2)} (${data.skew_3pct > 0 ? 'more short levels above' : data.skew_3pct < 0 ? 'more long levels below' : 'even'})`}</dd>
            </dl>
          ) : <p className={styles.muted}>{map.isLoading ? 'Estimating…' : 'No estimate yet.'}</p>}
          {data && (
            <p className={styles.muted}>
              Open interest {when(data.coverage.from)} to {when(data.coverage.to)} ({data.coverage.bars} bars). Assumed leverage {leverage}; maintenance margin {(data.assumptions.maintenance_margin * 100).toFixed(1)}%.
            </p>
          )}
          {data && <p className={styles.note}>{data.note}</p>}
        </aside>
      </div>
    </section>
  )
}
