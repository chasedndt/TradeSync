import type { CalendarEvent, OutlookKeyEvent } from '../api/types'
import { CaretDown, CaretUp } from './icons'
import { ReactionTable } from './thesis/KeyEvents'
import styles from './EventsStrip.module.css'

interface Props {
  event: CalendarEvent
  reaction?: OutlookKeyEvent
  open: boolean
  countdown: string
  onToggle: () => void
}

/**
 * One scheduled event on two lines: its rating, country and title, then when
 * it is and its measured reaction. A row with a reaction opens and closes when
 * clicked anywhere on it; the caret stays visible however narrow the panel, and
 * the open detail has its own hide control and keeps its table inside the panel.
 */
export function EventRow({ event: e, reaction: k, open, countdown, onToggle }: Props) {
  const lead = k?.reaction['BTC-PERP']?.['4h']
  const summary = lead?.median_abs_move_pct != null
    ? `BTC ${lead.median_abs_move_pct.toFixed(2)}% over 4h · ${lead.volatility_ratio?.toFixed(1) ?? '—'}× usual`
    : 'measured reaction'
  const rowClass = [styles.event, e.market_moving ? styles.moving : '', k ? styles.expandable : '', open ? styles.eventOpen : ''].join(' ')

  return (
    <li className={[styles.item, e.minutes_until < 0 ? styles.past : ''].join(' ')}>
      <div
        className={rowClass}
        role={k ? 'button' : undefined}
        tabIndex={k ? 0 : undefined}
        aria-expanded={k ? open : undefined}
        title={k ? (open ? 'Hide the measured reaction' : 'Show how the market reacted to past releases') : undefined}
        onClick={k ? onToggle : undefined}
        onKeyDown={k ? (ev) => {
          if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); onToggle() }
          if (ev.key === 'Escape' && open) onToggle()
        } : undefined}
      >
        <span className={`${styles.impact} ${styles[`impact${e.impact}`]}`} title={`${e.impact} impact (feed rating)`}>
          {e.impact === 'Holiday' ? 'HOL' : e.impact[0]}
        </span>
        <span className={styles.country}>{e.country}</span>
        {e.url ? (
          <a className={styles.name} href={e.url} target="_blank" rel="noopener noreferrer" title={`${e.title} · open ${e.source}`}
            onClick={(ev) => ev.stopPropagation()}>
            {e.title} ↗
          </a>
        ) : (
          <span className={styles.name} title={e.title}>{e.title}</span>
        )}
        <span className={styles.toggle}>{k ? (open ? <CaretUp size={13} weight="bold" /> : <CaretDown size={13} weight="bold" />) : null}</span>
        <span className={styles.meta}>
          <span className={styles.when}>{countdown}</span>
          {k ? (
            <span className={styles.reactionChip}>{summary}</span>
          ) : (e.forecast || e.previous) ? (
            <span className={styles.figures}>
              {e.forecast && <>forecast {e.forecast}</>}{e.forecast && e.previous && ' · '}{e.previous && <>previous {e.previous}</>}
            </span>
          ) : null}
        </span>
      </div>
      {open && k && (
        <div className={styles.detail}>
          <div className={styles.tableScroll}><ReactionTable reaction={k.reaction} /></div>
          {k.guidance.map((g, i) => <p key={i} className={styles.guidance}>{g}</p>)}
          {k.articles.length > 0 && (
            <ul className={styles.articles}>
              {k.articles.slice(0, 4).map((a) => (
                <li key={a.url}><a href={a.url} target="_blank" rel="noopener noreferrer">{a.title || a.url}</a> <span>{a.domain}</span></li>
              ))}
            </ul>
          )}
          <button type="button" className={styles.hide} onClick={onToggle}>Hide reaction <CaretUp size={11} weight="bold" /></button>
        </div>
      )}
    </li>
  )
}
