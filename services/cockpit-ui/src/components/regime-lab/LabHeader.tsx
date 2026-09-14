import type { UseQueryResult } from '@tanstack/react-query'
import type { RegimeLabOverview } from '../../api/regimeLabTypes'
import styles from './LabHeader.module.css'

interface Props {
  symbol: string
  symbols: string[]
  onSymbol: (symbol: string) => void
  overview: UseQueryResult<RegimeLabOverview, Error>
}

/** The page title, the market picker, and whether the evidence is live, counting fresh readings only. */
export function LabHeader({ symbol, symbols, onSymbol, overview }: Props) {
  const options = symbols.includes(symbol) ? symbols : [symbol, ...symbols]
  return (
    <header className={styles.header}>
      <div className={styles.title}>
        <h2>Regime Lab</h2>
        <p>Paper shadow: nothing here can activate a rulebook or place an order.</p>
      </div>
      <div className={styles.controls}>
        <label className={styles.market}>
          <span>Market</span>
          <select value={symbol} onChange={(event) => onSymbol(event.target.value)}>
            {options.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </label>
        <LivePill overview={overview} />
      </div>
    </header>
  )
}

function LivePill({ overview }: { overview: Props['overview'] }) {
  const health = overview.data?.health
  let tone = ''
  let label = 'Checking the evidence…'
  if (overview.isError) {
    tone = styles.down
    label = 'Overview unavailable'
  } else if (health) {
    if (health.market_data.status !== 'live') {
      tone = styles.down
      label = 'Market data offline'
    } else if (health.live) {
      tone = styles.live
      label = `Live · ${health.fresh_features} of ${health.feature_count} readings fresh`
    } else {
      tone = styles.stale
      label = 'Stale · no fresh readings'
    }
  }
  return (
    <span className={`${styles.pill} ${tone}`} role="status">
      <i aria-hidden="true" />
      {label}
    </span>
  )
}
