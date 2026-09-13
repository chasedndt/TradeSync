import { NavLink } from 'react-router-dom'
import { useEditions } from '../../api/hooks/useEditions'
import { hasOutlook } from '../thesis/guards'
import { RegenerateControl } from '../thesis/RegenerateControl'
import { formatPrice, formatWhen } from './format'
import styles from './Home.module.css'

const LEAN = { bearish: styles.leanBearish, bullish: styles.leanBullish, mixed: styles.leanMixed, none: styles.leanNone }

/** The Market Thesis at the top of Mission Control: lean, lead reads, notes, the next event that matters. */
export function MarketThesisCard() {
  const { data, isLoading, isError } = useEditions(1)
  const e = data?.editions[0]
  const o = e && hasOutlook(e.outlook) ? e.outlook : null
  const r = o?.breadth.reads
  const total = r ? Math.max(1, r.LONG + r.SHORT + r.NONE) : 1
  const nextEvent = o?.key_events.find((k) => k.minutes_until >= -60)

  return (
    <section className="panel" aria-labelledby="market-thesis-title">
      <div className="panel-heading">
        <div>
          <h2 id="market-thesis-title">Market Thesis</h2>
          <p>
            {e ? `${e.edition.replace('-', ' ')} edition · ${new Date(e.generated_at).toUTCString().slice(5, 22)} UTC${e.reason ? ` · ${e.reason}` : ''}` : isLoading ? 'loading…' : 'no edition yet'}
          </p>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <RegenerateControl withReason={false} />
          <NavLink to="/thesis" className="panel-action">Full thesis →</NavLink>
        </div>
      </div>

      {isError && <p className="tone-bad" style={{ padding: '10px 17px' }}>Thesis editions unavailable.</p>}
      {e && !o && <p className="tone-dim" style={{ padding: '10px 17px', margin: 0 }}>{e.headline} · regenerate to add the market outlook.</p>}

      {o && r && (
        <div className={styles.thesis}>
          <div className={styles.thesisMain}>
            <div className={styles.leanRow}>
              <span className={`${styles.lean} ${LEAN[o.breadth.lean]}`}>{o.breadth.lean.toUpperCase()}</span>
              <strong style={{ fontSize: 13 }}>{o.breadth.summary}</strong>
            </div>
            <div className={styles.readsBar} role="img" aria-label={`${r.LONG} long, ${r.SHORT} short, ${r.NONE} no read`}>
              <span className={styles.readsLong} style={{ width: `${(r.LONG / total) * 100}%` }} />
              <span className={styles.readsShort} style={{ width: `${(r.SHORT / total) * 100}%` }} />
              <span className={styles.readsNone} style={{ width: `${(r.NONE / total) * 100}%` }} />
            </div>
            <ul className={styles.notes}>
              {o.notes.slice(1, 5).map((n, i) => <li key={i}>{n}</li>)}
            </ul>
          </div>
          <div className={styles.thesisSide}>
            <span className={styles.sideTitle}>Lead reads</span>
            {o.leads.map((l) => (
              <div key={l.symbol} className={styles.lead}>
                <strong>{l.symbol.replace('-PERP', '')}</strong>
                <span className={`${styles.mono} ${l.direction === 'LONG' ? 'tone-good' : l.direction === 'SHORT' ? 'tone-bad' : 'tone-dim'}`}>
                  {l.direction === 'LONG' || l.direction === 'SHORT' ? l.direction : 'no read'}
                </span>
                <span className="metric-sub" style={{ margin: 0 }}>
                  {formatPrice(l.last)} · inval. {formatPrice(l.invalidation)} · {l.regime}
                </span>
              </div>
            ))}
            <span className={styles.sideTitle}>Next event</span>
            {nextEvent ? (
              <div className={styles.nextEvent}>
                <strong>{nextEvent.title}</strong> <span className="metric-sub" style={{ display: 'inline' }}>{formatWhen(nextEvent.minutes_until)}</span>
                {nextEvent.guidance[0] && <div className="metric-sub" style={{ lineHeight: 1.45 }}>{nextEvent.guidance[0]}</div>}
              </div>
            ) : (
              <span className="metric-sub">No High-impact event in the next seven days.</span>
            )}
          </div>
        </div>
      )}
    </section>
  )
}
