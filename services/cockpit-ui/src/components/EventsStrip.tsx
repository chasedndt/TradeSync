import { useEffect, useState } from 'react'
import { useEventReactions } from '../api/hooks/useHermes'
import type { CalendarEvent, ContextOverviewResponse, OutlookKeyEvent } from '../api/types'
import { CaretDown, CaretUp } from './icons'
import { ReactionTable } from './thesis/KeyEvents'
import styles from './EventsStrip.module.css'

interface Props {
  context: ContextOverviewResponse | undefined
}

const OPEN_KEY = 'tradesync.events.open'

/**
 * The week's scheduled economic events. Collapsible, and remembered. Each
 * market-moving event opens to show how the market measurably reacted to its
 * past releases, what that means for a trader, and recent coverage. Context
 * only: nothing here changes what the scorer does.
 */
export function EventsStrip({ context }: Props) {
  const provider = context?.providers.calendar
  const data = provider?.data
  const events = data?.events ?? []
  const reactions = useEventReactions()
  const [open, setOpen] = useState<boolean>(() => {
    try { return localStorage.getItem(OPEN_KEY) !== '0' } catch { return true }
  })
  const [detail, setDetail] = useState<string | null>(null)
  useEffect(() => {
    try { localStorage.setItem(OPEN_KEY, open ? '1' : '0') } catch { /* private window */ }
  }, [open])

  if (!provider || provider.status === 'disabled') return null

  // A key event stands for every variant of its release (CPI m/m, Core CPI m/m…), so each variant row gets its chip.
  const byKey = new Map<string, OutlookKeyEvent>(
    (reactions.data?.key_events ?? []).flatMap((k) =>
      [k.title, ...(k.related_titles ?? [])].map((title): [string, OutlookKeyEvent] => [`${title}|${k.scheduled_at?.slice(0, 10)}`, k]),
    ),
  )
  const shown = pickForStrip(events.filter((e) => e.minutes_until >= -60))
  const next = data?.next_market_moving ?? null

  return (
    <section className={`panel ${styles.strip}`} aria-labelledby="events-title">
      <button type="button" className={styles.head} onClick={() => setOpen(!open)} aria-expanded={open}>
        <span id="events-title" className={styles.title}>
          This week <span className={styles.sub}>scheduled events · measured reactions</span>
        </span>
        {next && (
          <span className={styles.next}>
            Next market-moving: <strong>{next.title}</strong> {formatCountdown(next.minutes_until, next.source)}
          </span>
        )}
        <span className={styles.caret}>{open ? <CaretUp size={14} /> : <CaretDown size={14} />}</span>
      </button>

      {open && (provider.status === 'unavailable' ? (
        <p className={styles.note}>Calendar feeds did not answer. Nothing is shown from memory.</p>
      ) : shown.length === 0 ? (
        <p className={styles.note}>No scheduled events in the next eight days from the configured feeds.</p>
      ) : (
        <ol className={styles.list}>
          {shown.map((e) => {
            const key = `${e.title}|${e.scheduled_at.slice(0, 10)}`
            const k = byKey.get(key)
            const isOpen = detail === key
            const lead = k?.reaction['BTC-PERP']?.['4h']
            return (
              <li key={`${e.source}:${e.scheduled_at}:${e.title}`} className={[styles.item, e.minutes_until < 0 ? styles.past : ''].join(' ')}>
                <div className={[styles.event, e.market_moving ? styles.moving : ''].join(' ')}>
                  <span className={`${styles.impact} ${styles[`impact${e.impact}`]}`} title={`${e.impact} impact (feed rating)`}>
                    {e.impact === 'Holiday' ? 'HOL' : e.impact[0]}
                  </span>
                  <span className={styles.country}>{e.country}</span>
                  {e.url ? (
                    <a className={styles.name} href={e.url} target="_blank" rel="noopener noreferrer" title={`Open ${e.source} for this event`}>{e.title} ↗</a>
                  ) : (
                    <span className={styles.name}>{e.title}</span>
                  )}
                  <span className={styles.when}>{formatCountdown(e.minutes_until, e.source)}</span>
                  {k ? (
                    <button type="button" className={styles.reactionChip} onClick={() => setDetail(isOpen ? null : key)} aria-expanded={isOpen}
                      title="How the market reacted to past releases">
                      {lead?.median_abs_move_pct != null ? `BTC ${lead.median_abs_move_pct.toFixed(2)}% · ${lead.volatility_ratio?.toFixed(1) ?? '—'}×` : 'reaction'}
                      {isOpen ? ' ▴' : ' ▾'}
                    </button>
                  ) : (
                    <span className={styles.figures}>
                      {e.forecast && <>f {e.forecast}</>}{e.forecast && e.previous && ' · '}{e.previous && <>p {e.previous}</>}
                    </span>
                  )}
                </div>
                {isOpen && k && (
                  <div className={styles.detail}>
                    <ReactionTable reaction={k.reaction} />
                    {k.guidance.map((g, i) => <p key={i} className={styles.guidance}>{g}</p>)}
                    {k.articles.length > 0 && (
                      <ul className={styles.articles}>
                        {k.articles.slice(0, 4).map((a) => (
                          <li key={a.url}><a href={a.url} target="_blank" rel="noopener noreferrer">{a.title || a.url}</a> <span>{a.domain}</span></li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
              </li>
            )
          })}
        </ol>
      ))}

      {open && (
        <p className={styles.foot}>
          Sources: {(data?.sources ?? ['forexfactory']).join(', ')}
          {data?.fred_configured === false && ' · FRED release dates need the free FRED key'}
          {' · '}
          {reactions.data?.computed_at ? `reactions measured ${new Date(reactions.data.computed_at).toUTCString().slice(5, 22)} UTC` : reactions.data?.computing ? 'measuring reactions…' : 'reactions not yet measured'}
          {provider.stale && ' · feed cache is stale'}
        </p>
      )}
    </section>
  )
}

/** Up to eight lines: every market-moving event first, then the nearest others. */
function pickForStrip(events: CalendarEvent[]): CalendarEvent[] {
  const moving = events.filter((e) => e.market_moving)
  const rest = events.filter((e) => !e.market_moving && e.impact !== 'Low')
  return [...moving, ...rest].sort((a, b) => a.minutes_until - b.minutes_until).slice(0, 8)
}

function formatCountdown(minutes: number, source: CalendarEvent['source']): string {
  if (source === 'fred') {
    const days = Math.round(minutes / 1440)
    return days <= 0 ? 'today (date only)' : days === 1 ? 'tomorrow (date only)' : `in ${days}d (date only)`
  }
  if (minutes < 0) return `${-minutes}m ago`
  if (minutes < 60) return `in ${minutes}m`
  if (minutes < 1440) return `in ${Math.floor(minutes / 60)}h ${minutes % 60}m`
  const days = Math.floor(minutes / 1440)
  return `in ${days}d ${Math.floor((minutes % 1440) / 60)}h`
}
