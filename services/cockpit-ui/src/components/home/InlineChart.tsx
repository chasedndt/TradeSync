import { useState } from 'react'
import { NavLink } from 'react-router-dom'
import { useCandles } from '../../api/hooks/useCandles'
import { PriceChart } from '../canvas/PriceChart'
import { formatPrice } from './format'
import styles from './Home.module.css'

const TIMEFRAMES = ['5m', '15m', '1h', '4h']

/** The chart that opens under a market row: timeframe chips, the window's change, and a link to the full canvas. */
export function InlineChart({ symbol }: { symbol: string }) {
  const [timeframe, setTimeframe] = useState('15m')
  const { data, isLoading, isError } = useCandles(symbol, timeframe, 160)
  const candles = data?.candles ?? []
  const first = candles[0]
  const last = candles[candles.length - 1]
  const change = first && last ? ((last.close - first.open) / first.open) * 100 : null

  return (
    <div className={styles.inline} onClick={(e) => e.stopPropagation()}>
      <div className={styles.inlineControls}>
        {TIMEFRAMES.map((tf) => (
          <button key={tf} type="button" className={tf === timeframe ? 'chip chip--active' : 'chip'} onClick={() => setTimeframe(tf)} aria-pressed={tf === timeframe}>
            {tf}
          </button>
        ))}
        <span className={styles.inlineReadout}>
          <span className="metric-main">{last ? formatPrice(last.close) : '—'}</span>
          <span className={`metric-sub ${change == null ? '' : change >= 0 ? 'tone-good' : 'tone-bad'}`} style={{ margin: 0 }}>
            {change == null ? '' : `${change >= 0 ? '+' : ''}${change.toFixed(2)}% over ${candles.length} candles`}
          </span>
          <NavLink to={`/canvas?symbol=${symbol}&interval=${timeframe}`} className="panel-action">Full canvas →</NavLink>
        </span>
      </div>
      {isError ? (
        <p className="tone-bad" style={{ margin: 0 }}>Candles unavailable. Nothing is drawn in their place.</p>
      ) : isLoading ? (
        <p className="tone-dim" style={{ margin: 0 }}>Loading candles…</p>
      ) : candles.length === 0 ? (
        <p className="tone-dim" style={{ margin: 0 }}>No candles for this window.</p>
      ) : (
        <PriceChart candles={candles} height={240} />
      )}
    </div>
  )
}
