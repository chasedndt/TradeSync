import type { UseQueryResult } from '@tanstack/react-query'
import type { RegimeLabOverview } from '../../api/regimeLabTypes'
import { REASON_HINTS, REASON_LABELS, REASON_ORDER, count, duration, percent } from './format'
import styles from './HealthStrip.module.css'

/** Where the evidence stands: fresh inputs, why coverage is what it is, and each feed's age against its stale limit. */
export function HealthStrip({ overview }: { overview: UseQueryResult<RegimeLabOverview, Error> }) {
  const { data, error, isLoading } = overview
  if (isLoading) {
    return <section className={`panel ${styles.strip}`}><p className={styles.note}>Reading market data…</p></section>
  }
  if (!data) {
    return (
      <section className={`panel ${styles.strip}`}>
        <p className={`${styles.note} tone-bad`}>Evidence health unavailable: {error?.message ?? 'no response'}</p>
      </section>
    )
  }

  const { health, baseline_evaluation: evaluation } = data
  const scoring = data.feature_results.filter((feature) => feature.scoring_allowed).length
  const online = health.market_data.status === 'live'
  const readAt = new Date(health.evaluated_at_ms).toISOString().slice(11, 19)
  const caps = evaluation.risk_caps_applied.map((cap) => cap.flag.split('_').join(' ')).join(', ')

  return (
    <section className={`panel ${styles.strip}`} aria-label="Evidence health">
      {error && <p className={`${styles.note} tone-warn`}>The latest refresh failed: {error.message}. Showing the reading from {readAt} UTC.</p>}
      <div className={styles.stats}>
        <Stat
          label="Live inputs"
          value={`${health.fresh_features}/${health.feature_count}`}
          sub="fresh: within their stale limit"
          tone={health.fresh_features > 0 ? styles.good : styles.warn}
        />
        <Stat label="Scoring coverage" value={percent(evaluation.data_coverage)} sub={`${scoring} ${scoring === 1 ? 'feature' : 'features'} scoring now`} />
        <Stat label="Paper-risk ceiling" value={`${evaluation.paper_risk_multiplier.toFixed(2)}×`} sub={caps ? `capped by ${caps}` : 'no cap applied'} />
        <Stat
          label="Market data"
          value={online ? 'online' : 'offline'}
          sub={online ? `${count(health.market_data.observation_count)} observations · read ${readAt} UTC` : health.market_data.reason ?? 'no reason given'}
          tone={online ? styles.good : styles.bad}
        />
      </div>
      <ul className={styles.reasons} aria-label="Why coverage is what it is">
        {REASON_ORDER.map((reason) => {
          const n = health.coverage_reasons[reason] ?? 0
          return (
            <li key={reason} className={`${styles.reason} ${n === 0 ? styles.zero : ''}`} data-reason={reason} title={REASON_HINTS[reason]}>
              <b>{n}</b>{REASON_LABELS[reason]}
            </li>
          )
        })}
      </ul>
      <ul className={styles.feeds} aria-label="Feeds">
        {health.feeds.map((feed) => {
          const withoutReading = feed.features - feed.observed
          return (
            <li key={feed.feed} className={styles.feed} data-status={feed.status}>
              <span className={styles.feedName}>{feed.feed}</span>
              <span className={styles.feedCount}>{feed.fresh}/{feed.features} fresh</span>
              <span className={styles.feedAge}>
                {feed.observed === 0
                  ? 'no reading'
                  : `newest ${duration(feed.newest_age_ms)} old · stale after ${duration(feed.stale_after_ms)}${withoutReading > 0 ? ` · ${withoutReading} without a reading` : ''}`}
              </span>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

function Stat({ label, value, sub, tone = '' }: { label: string; value: string; sub: string; tone?: string }) {
  return (
    <div className={`${styles.stat} ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{sub}</small>
    </div>
  )
}
