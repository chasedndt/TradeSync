import type { CalendarEvent, ContextOverviewResponse } from '../api/types'
import styles from './EventsStrip.module.css'

interface Props {
  context: ContextOverviewResponse | undefined
}

/**
 * The week's scheduled economic events, on Mission Control.
 *
 * First of the evidence sources from the 2026-09-12 research. Context only:
 * an event here changes nothing the scorer does. It exists so the operator
 * sees a CPI print or an FOMC decision coming before the chart reacts to it.
 *
 * Every line names its source. ForexFactory is a courtesy feed with
 * unpublished terms, fetched hourly; FRED is official but date-only and needs
 * the same free key the macro provider wants.
 */
export function EventsStrip({ context }: Props) {
  const provider = context?.providers.calendar
  const data = provider?.data
  const events = data?.events ?? []

  if (!provider || provider.status === 'disabled') return null

  const upcoming = events.filter((e) => e.minutes_until >= -60)
  const shown = pickForStrip(upcoming)
  const next = data?.next_market_moving ?? null

  return (
    <section className={`panel ${styles.strip}`} aria-labelledby="events-title">
      <div className={styles.head}>
        <span id="events-title" className={styles.title}>
          This week <span className={styles.sub}>scheduled events · context only</span>
        </span>
        {next && (
          <span className={styles.next}>
            Next market-moving: <strong>{next.title}</strong> {formatCountdown(next.minutes_until, next.source)}
          </span>
        )}
      </div>

      {provider.status === 'unavailable' ? (
        <p className={styles.note}>Calendar feeds did not answer. Nothing is shown from memory.</p>
      ) : shown.length === 0 ? (
        <p className={styles.note}>No scheduled events in the next eight days from the configured feeds.</p>
      ) : (
        <ol className={styles.list}>
          {shown.map((e) => (
            <li
              key={`${e.source}:${e.scheduled_at}:${e.title}`}
              className={[
                styles.event,
                e.market_moving ? styles.moving : '',
                e.minutes_until < 0 ? styles.past : '',
              ].join(' ')}
            >
              <span className={`${styles.impact} ${styles[`impact${e.impact}`]}`} title={`${e.impact} impact (feed rating)`}>
                {e.impact === 'Holiday' ? 'HOL' : e.impact[0]}
              </span>
              <span className={styles.country}>{e.country}</span>
              <span className={styles.name}>{e.title}</span>
              <span className={styles.when}>{formatCountdown(e.minutes_until, e.source)}</span>
              {(e.forecast || e.previous) && (
                <span className={styles.figures}>
                  {e.forecast && <>f {e.forecast}</>}
                  {e.forecast && e.previous && ' · '}
                  {e.previous && <>p {e.previous}</>}
                </span>
              )}
            </li>
          ))}
        </ol>
      )}

      <p className={styles.foot}>
        Sources: {(data?.sources ?? ['forexfactory']).join(', ')}
        {data?.fred_configured === false && ' · FRED release dates need the free FRED key'}
        {' · '}
        {data?.counts?.rejected ? `${data.counts.rejected} malformed events dropped` : 'all events validated'}
        {provider.stale && ' · feed cache is stale'}
      </p>
    </section>
  )
}

/** Up to eight lines: every market-moving event first, then the nearest others. */
function pickForStrip(events: CalendarEvent[]): CalendarEvent[] {
  const moving = events.filter((e) => e.market_moving)
  const rest = events.filter((e) => !e.market_moving && e.impact !== 'Low')
  return [...moving, ...rest]
    .sort((a, b) => a.minutes_until - b.minutes_until)
    .slice(0, 8)
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
