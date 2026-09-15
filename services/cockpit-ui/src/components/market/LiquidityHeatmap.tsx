import { useMemo, useState } from 'react'
import { useLiquidityHeatmap, useWindowCandles } from '../../api/hooks/useLiquidity'
import type { HeatmapWindow, LiquidityHeatmap as Heatmap } from '../../api/liquidityTypes'
import { price } from '../ledger/format'
import { coverageLine } from './heatmap/coverage'
import { HeatmapChart } from './heatmap/HeatmapChart'
import type { HeatLayer } from './heatmap/HeatmapPrimitive'
import { gradient, intensity, restingColour } from './heatmap/palette'
import { usdCompact, when } from './marketFormat'
import styles from './LiquidityPanels.module.css'

const WINDOWS: { key: HeatmapWindow; interval: string; limit: number }[] = [
  { key: '6h', interval: '5m', limit: 72 },
  { key: '24h', interval: '15m', limit: 96 },
  { key: '3d', interval: '1h', limit: 72 },
  { key: '7d', interval: '1h', limit: 168 },
  { key: '30d', interval: '4h', limit: 180 },
]
type Sides = 'both' | 'bids' | 'asks'

function toLayer(data: Heatmap, sides: Sides): HeatLayer {
  const step = data.price_step ?? 0
  const priceEdges = data.prices.map((p): [number, number] => [p - step / 2, p + step / 2])
  const reference = data.p95_usd || data.max_usd
  const pick = (rows: [number, number, number][]) => rows.map(([t, p, usd]) => ({ t, p, intensity: intensity(usd, reference) }))
  const cells = [...(sides !== 'asks' ? pick(data.bids) : []), ...(sides !== 'bids' ? pick(data.asks) : [])]
  return { times: data.times, bucketSeconds: data.bucket_seconds, priceEdges, cells, colour: restingColour }
}

/**
 * Resting Hyperliquid liquidity over time: where orders sat below and above
 * price, bucket by bucket, from books recorded once a minute. Brighter cells hold
 * more resting notional; the largest walls near price are marked on the chart.
 */
export function LiquidityHeatmap({ symbol }: { symbol: string }) {
  const [window, setWindow] = useState<HeatmapWindow>('24h')
  const [sides, setSides] = useState<Sides>('both')
  const spec = WINDOWS.find((w) => w.key === window) ?? WINDOWS[1]
  const heat = useLiquidityHeatmap(symbol, window)
  const candles = useWindowCandles(symbol, spec.interval, spec.limit)
  const data = heat.data?.window === window && heat.data.symbol === symbol ? heat.data : undefined
  const layer = useMemo(() => (data ? toLayer(data, sides) : null), [data, sides])
  const walls = data?.latest?.walls
  const levels = useMemo(() => [
    ...(walls?.below ? [{ price: walls.below.price, colour: '#3fb27f', title: `bid wall ${usdCompact(walls.below.usd)}` }] : []),
    ...(walls?.above ? [{ price: walls.above.price, colour: '#e0574a', title: `ask wall ${usdCompact(walls.above.usd)}` }] : []),
  ], [walls])

  return (
    <section className={`panel ${styles.panel}`} aria-labelledby="liquidity-heatmap-title">
      <header className={styles.head}>
        <div>
          <h3 id="liquidity-heatmap-title">Resting liquidity heatmap</h3>
          <p>Hyperliquid orders resting below and above price, recorded every minute and aggregated to {data?.n_sig_figs ?? '—'} significant figures.</p>
        </div>
        <div className={styles.controls}>
          <div className={styles.chips} role="group" aria-label="Window">
            {WINDOWS.map((w) => (
              <button key={w.key} type="button" className={w.key === window ? 'chip chip--active' : 'chip'} aria-pressed={w.key === window} onClick={() => setWindow(w.key)}>{w.key}</button>
            ))}
          </div>
          <div className={styles.chips} role="group" aria-label="Sides">
            {(['both', 'bids', 'asks'] as Sides[]).map((s) => (
              <button key={s} type="button" className={s === sides ? 'chip chip--active' : 'chip'} aria-pressed={s === sides} onClick={() => setSides(s)}>{s}</button>
            ))}
          </div>
        </div>
      </header>
      <div className={styles.body}>
        <div className={styles.chartCol}>
          {heat.isError && <p className={styles.warn}>Heatmap unavailable: {(heat.error as Error).message}</p>}
          <HeatmapChart candles={candles.data ?? []} layer={layer} intraday={spec.interval !== '1d'} levels={levels} />
          <div className={styles.legend}>
            <span>less</span><i style={{ background: gradient(restingColour) }} /><span>{data ? `${usdCompact(data.p95_usd)}+ resting per level` : 'more'}</span>
          </div>
        </div>
        <aside className={styles.side}>
          <h4>Near price now</h4>
          {walls ? (
            <dl>
              <dt>Largest bid wall</dt><dd>{walls.below ? `${price(walls.below.price)} · ${usdCompact(walls.below.usd)} · ${(walls.below.distance_bps / 100).toFixed(2)}%` : 'none within 5%'}</dd>
              <dt>Largest ask wall</dt><dd>{walls.above ? `${price(walls.above.price)} · ${usdCompact(walls.above.usd)} · +${(walls.above.distance_bps / 100).toFixed(2)}%` : 'none within 5%'}</dd>
              <dt>Bids vs asks within 5%</dt><dd>{usdCompact(walls.bid_usd)} vs {usdCompact(walls.ask_usd)}{walls.imbalance != null ? ` (balance ${walls.imbalance > 0 ? '+' : ''}${walls.imbalance.toFixed(2)})` : ''}</dd>
            </dl>
          ) : <p className={styles.muted}>{heat.isLoading ? 'Loading recorded books…' : 'No recent book recorded.'}</p>}
          {data && <p className={styles.muted}>{coverageLine(data, when)}</p>}
          {data && <p className={styles.note}>{data.note}</p>}
        </aside>
      </div>
    </section>
  )
}
