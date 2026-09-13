import type { MarketOutlook } from '../../api/types'
import { formatPrice } from '../home/format'
import styles from './Thesis.module.css'

/** The first thing a trader reads: the lean of the market, the lead reads, and the notes that follow from them. */
export function OutlookOverview({ o }: { o: MarketOutlook }) {
  const r = o.breadth.reads
  const total = Math.max(1, r.LONG + r.SHORT + r.NONE)
  return (
    <div className={styles.overview}>
      <div className={styles.leanRow}>
        <span className={`${styles.lean} ${styles[o.breadth.lean]}`}>{o.breadth.lean.toUpperCase()}</span>
        <strong>{o.breadth.summary}</strong>
      </div>
      <div className={styles.readsBar} role="img" aria-label={`${r.LONG} long, ${r.SHORT} short, ${r.NONE} no read`}>
        <span className={styles.readsLong} style={{ width: `${(r.LONG / total) * 100}%` }} />
        <span className={styles.readsShort} style={{ width: `${(r.SHORT / total) * 100}%` }} />
        <span className={styles.readsNone} style={{ width: `${(r.NONE / total) * 100}%` }} />
      </div>
      <div className={styles.readsLegend}>
        <span className="tone-good">{r.LONG} long</span>
        <span className="tone-bad">{r.SHORT} short</span>
        <span>{r.NONE} no read</span>
        <span>regimes: {Object.entries(o.breadth.regimes).map(([k, v]) => `${v} ${k}`).join(', ')}</span>
        <span>{o.breadth.meaning}</span>
      </div>
      <div className={styles.leads}>
        {o.leads.map((l) => (
          <div key={l.symbol} className={styles.lead}>
            <strong>
              {l.symbol.replace('-PERP', '')}{' '}
              <span className={l.direction === 'LONG' ? 'tone-good' : l.direction === 'SHORT' ? 'tone-bad' : 'tone-dim'}>
                {l.direction === 'LONG' || l.direction === 'SHORT' ? l.direction : 'no read'}
              </span>
            </strong>
            <span className="metric-sub">{l.regime} regime · {l.verdict} · coverage {l.coverage != null ? l.coverage.toFixed(2) : '—'}</span>
            <span>last {formatPrice(l.last)} · 24h {formatPrice(l.low_24h)} to {formatPrice(l.high_24h)}</span>
            <span>invalidation <b className="tone-warn">{formatPrice(l.invalidation)}</b></span>
          </div>
        ))}
      </div>
      <ul className={styles.notes}>
        {o.notes.slice(1).map((n, i) => <li key={i}>{n}</li>)}
      </ul>
    </div>
  )
}
