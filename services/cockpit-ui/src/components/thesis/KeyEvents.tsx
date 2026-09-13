import type { EventReactionHorizon, MarketOutlook, OutlookKeyEvent } from '../../api/types'
import { formatWhen } from '../home/format'
import styles from './Thesis.module.css'

const HORIZONS = ['1h', '4h', '24h'] as const

/** The measured reaction of past releases: median move, multiple of an ordinary move, share up, sample size. */
export function ReactionTable({ reaction }: { reaction: OutlookKeyEvent['reaction'] }) {
  const symbols = Object.keys(reaction)
  if (symbols.length === 0) return <span className="metric-sub">No measured history for this event kind.</span>
  return (
    <table className={styles.reaction}>
      <thead>
        <tr><th>past releases</th>{HORIZONS.map((h) => <th key={h}>{h} after</th>)}</tr>
      </thead>
      <tbody>
        {symbols.map((s) => (
          <tr key={s}>
            <th>{s.replace('-PERP', '')}</th>
            {HORIZONS.map((h) => <td key={h}><Cell h={reaction[s][h]} /></td>)}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function Cell({ h }: { h?: EventReactionHorizon }) {
  if (!h || !h.n || h.median_abs_move_pct == null) return <span className="tone-dim">—</span>
  const ratio = h.volatility_ratio
  const up = h.up_share != null ? Math.round(h.up_share * 100) : null
  return (
    <span title={`${h.n} releases · median range ${h.median_range_pct ?? '—'}% · ordinary day ${h.baseline_median_abs_move_pct ?? '—'}% (${h.baseline_days} days)`}>
      <strong className={ratio != null && ratio >= 1.5 ? 'tone-warn' : undefined}>{h.median_abs_move_pct.toFixed(2)}%</strong>
      <small> {ratio != null ? `${ratio.toFixed(1)}× usual` : ''}{up != null ? ` · up ${up}%` : ''} · n {h.n}</small>
    </span>
  )
}

function EventCard({ e }: { e: OutlookKeyEvent }) {
  return (
    <article className={styles.event}>
      <div className={styles.eventHead}>
        <span className={`${styles.impact} ${e.impact === 'High' ? styles.impactHigh : styles.impactMedium}`}>{e.impact ?? 'event'}</span>
        {e.url ? (
          <a href={e.url} target="_blank" rel="noopener noreferrer" className={styles.eventTitle}>{e.title} ↗</a>
        ) : (
          <span className={styles.eventTitle}>{e.title}</span>
        )}
        <span className="metric-sub">
          {e.country ?? ''} · {formatWhen(e.minutes_until)} · {new Date(e.scheduled_at).toUTCString().slice(0, 22)} UTC
        </span>
        {(e.forecast || e.previous) && <span className="metric-sub">forecast {e.forecast || '—'} · previous {e.previous || '—'}</span>}
      </div>
      <ReactionTable reaction={e.reaction} />
      {e.guidance.map((g, i) => <p key={i} className={styles.guidance}>{g}</p>)}
      {e.articles.length > 0 && (
        <ul className={styles.articles}>
          {e.articles.map((a) => (
            <li key={a.url}>
              <a href={a.url} target="_blank" rel="noopener noreferrer">{a.title || a.url}</a> <span className="metric-sub">{a.domain}</span>
            </li>
          ))}
        </ul>
      )}
    </article>
  )
}

/** This week's High-impact and market-moving events, each with how the market reacted before and recent coverage. */
export function KeyEvents({ events, method }: { events: OutlookKeyEvent[]; method?: MarketOutlook['reaction_method'] }) {
  return (
    <div className={styles.events}>
      {events.length === 0 && <p className="tone-dim" style={{ margin: 0 }}>No High-impact or market-moving event in the next seven days from the configured feeds.</p>}
      {events.map((e) => <EventCard key={`${e.title}|${e.scheduled_at}`} e={e} />)}
      {method && <p className={styles.foot}>Measured: {method.measure}. Baseline: {method.baseline}. {method.caveat}.</p>}
    </div>
  )
}
