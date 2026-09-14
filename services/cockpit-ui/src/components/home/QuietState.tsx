import { Link } from 'react-router-dom'
import { useOpportunityLifecycle } from '../../api/hooks/useOpportunityLifecycle'
import { since } from '../ledger/format'
import styles from './QuietState.module.css'

/**
 * What the scorer has been doing while no opportunity is live: when the last
 * one was, and which gates refused its verdicts over the recent window.
 */
export function QuietState({ windowMinutes = 60 }: { windowMinutes?: number }) {
  const { data, isLoading, isError } = useOpportunityLifecycle(windowMinutes)

  if (isLoading) return <p className={styles.message}>No live opportunity. Checking the scorer's recent verdicts…</p>
  if (isError || !data) return <p className={styles.message}>No live opportunity. The scorer's recent verdicts could not be read.</p>

  const last = data.last_opportunity
  const { verdicts } = data
  return (
    <div className={styles.quiet} role="status">
      <p className={styles.lead}>
        No live opportunity.{' '}
        {last ? (
          <>
            The last was <Link to={`/opportunities/${last.id}`}>{last.symbol.replace('-PERP', '')} {last.direction}</Link>, opened{' '}
            {since(last.opened_at)}{last.expires_at ? `, expired ${since(last.expires_at)}` : ''}.
          </>
        ) : (
          'None has been recorded yet.'
        )}
      </p>
      <p className={styles.sub}>
        Last {data.window_minutes} minutes: {verdicts.total} verdicts, {verdicts.admitted} admitted, {verdicts.refused} refused
        {verdicts.last_verdict_at ? ` · newest ${since(verdicts.last_verdict_at)}` : ' · no verdict recorded in this window'}.
      </p>
      {data.top_refusal_reasons.length > 0 && (
        <>
          <ol className={styles.reasons} aria-label="Top refusal reasons">
            {data.top_refusal_reasons.map((reason) => (
              <li key={reason.code}>
                <span className={styles.reasonLabel}>{reason.label}</span>
                <span className={styles.count}>
                  {reason.refusals} · {reason.share_of_refusals == null ? '—' : `${Math.round(reason.share_of_refusals * 100)}%`}
                </span>
                {reason.example_detail && <span className={styles.detail}>{reason.example_detail}</span>}
              </li>
            ))}
          </ol>
          <p className={styles.note}>{data.note}</p>
        </>
      )}
    </div>
  )
}
