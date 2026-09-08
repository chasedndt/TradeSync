import { useState } from 'react'
import { NavLink } from 'react-router-dom'
import { useCandles } from '../../api/hooks/useCandles'
import { PriceChart } from './PriceChart'

const SYMBOLS = ['BTC-PERP', 'ETH-PERP', 'SOL-PERP']
const INTERVALS = ['5m', '15m', '1h', '4h']

/**
 * A live chart on Mission Control itself.
 *
 * Mission Control is where the operator starts, so the price belongs here
 * rather than one navigation away. This is the compact read; the full canvas
 * carries evidence markers and the longer window.
 */
export function MarketChartPanel() {
  const [symbol, setSymbol] = useState(SYMBOLS[0])
  const [interval, setInterval] = useState('15m')
  const { data, isLoading, isError } = useCandles(symbol, interval, 120)

  const candles = data?.candles ?? []
  const last = candles.length ? candles[candles.length - 1] : undefined
  const first = candles.length ? candles[0] : undefined
  const change = first && last ? ((last.close - first.open) / first.open) * 100 : null

  return (
    <section className="panel chart-panel" aria-labelledby="market-chart-title">
      <div className="panel-heading">
        <div>
          <h2 id="market-chart-title">Price Charts</h2>
          <p>Hyperliquid candles · display only</p>
        </div>
        <div className="panel-actions">
          <NavLink to={`/canvas?symbol=${symbol}&interval=${interval}`} className="panel-action">
            Full canvas →
          </NavLink>
        </div>
      </div>

      <div className="chart-panel__controls">
        <div className="chart-panel__group" role="group" aria-label="Market">
          {SYMBOLS.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setSymbol(s)}
              className={s === symbol ? 'chip chip--active' : 'chip'}
              aria-pressed={s === symbol}
            >
              {s.replace('-PERP', '')}
            </button>
          ))}
        </div>

        <div className="chart-panel__group" role="group" aria-label="Timeframe">
          {INTERVALS.map((i) => (
            <button
              key={i}
              type="button"
              onClick={() => setInterval(i)}
              className={i === interval ? 'chip chip--active' : 'chip'}
              aria-pressed={i === interval}
            >
              {i}
            </button>
          ))}
        </div>

        <div className="chart-panel__readout">
          <span className="metric-main">{last ? formatPrice(last.close) : '—'}</span>
          <span className={`metric-sub ${change == null ? '' : change >= 0 ? 'tone-good' : 'tone-bad'}`}>
            {change == null ? 'no window' : `${change >= 0 ? '+' : ''}${change.toFixed(2)}% this window`}
          </span>
        </div>
      </div>

      {isError ? (
        <p className="tone-bad chart-panel__message">
          Charts unavailable — the venue did not answer. No substitute series is drawn.
        </p>
      ) : isLoading ? (
        <p className="tone-dim chart-panel__message">Loading candles…</p>
      ) : candles.length === 0 ? (
        <p className="tone-dim chart-panel__message">
          No candles returned for this window. Nothing is interpolated.
        </p>
      ) : (
        <PriceChart candles={candles} height={260} />
      )}
    </section>
  )
}

function formatPrice(value: number): string {
  return `$${value.toLocaleString('en-US', {
    minimumFractionDigits: value < 1000 ? 2 : 1,
    maximumFractionDigits: value < 1000 ? 2 : 1,
  })}`
}
