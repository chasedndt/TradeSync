import { useEffect, useState } from 'react'
import { useEventReactions } from '../api/hooks/useHermes'
import type { CalendarEvent, ContextOverviewResponse, OutlookKeyEvent } from '../api/types'
import { EventRow } from './EventRow'
import { CaretDown, CaretUp } from './icons'
import styles from './EventsStrip.module.css'

interface Props {
  context: ContextOverviewResponse | undefined
}

const OPEN_KEY = 'tradesync.events.open'

/**
 * The week's scheduled economic events. Collapsible, and remembered. Each
 * market-moving event opens to show how the market measurably reacted to its
 * past releases, what that means for a trader, and recent coverage; it closes
 * from the row, its hide control, or Escape. Context only: nothing here changes
 * what the scorer does.
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
  useEffect(() => {
    if (!detail) return
    const onKey = (ev: KeyboardEvent) => { if (ev.key === 'Escape') setDetail(null) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [detail])

  if (!provider || provider.status === 'disabled') return null

  // A key event stands for every variant of its release (CPI m/m, Core CPI m/m…), so each variant row gets its reaction.
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
        <span className={styles.caret}>{open ? <CaretUp size={14} /> : <CaretDown size={14} />}</span>
        {next && (
          <span className={styles.next}>
            Next market-moving: <strong>{next.title}</strong> {formatCountdown(next.minutes_until, next.source)}
          </span>
        )}
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
            // Only a measured reaction (or coverage) opens: a key event with neither would open to "no history".
            const reaction = k && (Object.keys(k.reaction).length > 0 || k.articles.length > 0) ? k : undefined
            return (
              <EventRow
                key={`${e.source}:${e.scheduled_at}:${e.title}`}
                event={e}
                reaction={reaction}
                open={detail === key}
                countdown={formatCountdown(e.minutes_until, e.source)}
                onToggle={() => setDetail(detail === key ? null : key)}
              />
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
