import { useMemo } from 'react'
import type { LabEquity } from '../../api/strikezoneTypes'
import { share, usd } from './format'
import styles from './EquityCurve.module.css'

const W = 800
const H = 180
const PAD = 8

/** Cumulative net P&L of every resolved paper trade in exit order, after fees, slippage and funding. */
export function EquityCurve({ equity, notional }: { equity: LabEquity; notional: number | null }) {
  const geometry = useMemo(() => {
    const points = equity.points
    if (points.length < 2) return null
    const values = points.map((p) => p.cumulative)
    const lo = Math.min(0, ...values)
    const hi = Math.max(0, ...values)
    const span = hi - lo || 1
    const x = (i: number) => PAD + (i / (points.length - 1)) * (W - 2 * PAD)
    const y = (v: number) => PAD + (1 - (v - lo) / span) * (H - 2 * PAD)
    const line = points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.cumulative).toFixed(1)}`).join(' ')
    const area = `${line} L${x(points.length - 1).toFixed(1)},${y(0).toFixed(1)} L${x(0).toFixed(1)},${y(0).toFixed(1)} Z`
    return { line, area, zero: y(0), lo, hi, first: points[0].t, last: points[points.length - 1].t }
  }, [equity.points])
  const negative = equity.net_pnl_usdc < 0

  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h3>Paper equity</h3>
          <p>
            cumulative net P&amp;L after fees, slippage and funding · {equity.trades} resolved trades
            {notional ? ` · $${notional.toLocaleString()} paper notional per trade` : ''}
          </p>
        </div>
      </div>
      <div className={styles.stats}>
        <span>net <b className={negative ? 'tone-bad' : 'tone-good'}>{usd(equity.net_pnl_usdc)}</b></span>
        <span>won <b>{share(equity.win_rate)}</b></span>
        <span>max drawdown <b className="tone-bad">{usd(-equity.max_drawdown_usdc)}</b></span>
      </div>
      {geometry ? (
        <div className={styles.chart}>
          <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label={`Cumulative paper P&L, ending at ${usd(equity.net_pnl_usdc)}`}>
            <line x1={0} x2={W} y1={geometry.zero} y2={geometry.zero} className={styles.zero} />
            <path d={geometry.area} className={negative ? styles.areaBad : styles.areaGood} />
            <path d={geometry.line} className={negative ? styles.lineBad : styles.lineGood} vectorEffect="non-scaling-stroke" />
          </svg>
          <div className={styles.axis}>
            <span>{geometry.first.slice(0, 10)}</span>
            <span>high {usd(geometry.hi)} · low {usd(geometry.lo)}</span>
            <span>{geometry.last.slice(0, 10)}</span>
          </div>
        </div>
      ) : (
        <p className={styles.empty}>Fewer than two resolved trades so far.</p>
      )}
    </section>
  )
}
