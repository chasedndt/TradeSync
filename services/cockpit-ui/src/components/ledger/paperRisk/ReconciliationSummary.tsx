import type { UseQueryResult } from '@tanstack/react-query'
import type { Reconciliation } from '../../../api/paperRiskTypes'
import { ageText, codeLabel, utcStamp } from './paperRiskFormat'
import styles from './ReconciliationSummary.module.css'

const STATUS = {
  clean: { text: 'Clean', tone: 'tone-good' },
  mismatch: { text: 'Mismatch · new entries paused', tone: 'tone-bad' },
  failed: { text: 'Failed · new entries refused', tone: 'tone-bad' },
}

/** The last restart reconciliation: when it ran, what it checked, every mismatch, and every observation gap. */
export function ReconciliationSummary({ reconciliation }: { reconciliation: UseQueryResult<Reconciliation, Error> }) {
  const data = reconciliation.data
  const last = data?.last_run
  return (
    <div className={styles.summary}>
      <h4>Last reconciliation</h4>
      {reconciliation.isError && <p role="alert" className="tone-warn">Reconciliation state unavailable: {reconciliation.error.message}</p>}
      {data && !last && <p className="tone-warn">No reconciliation recorded yet; new entries are refused until one runs clean.</p>}
      {last && (
        <>
          <p>
            <strong className={STATUS[last.status].tone}>{STATUS[last.status].text}</strong> · finished {utcStamp(last.finished_at)} · {last.trigger} run ·{' '}
            {last.positions_checked} positions checked, {last.open_positions} open
          </p>
          {last.error && <p className="tone-bad">{last.error}</p>}
          {last.mismatches.length > 0 && (
            <ul className={styles.list}>
              {last.mismatches.map((m, index) => (
                <li key={`${m.code}-${index}`}>
                  <span>{codeLabel(m.code)}</span> {m.detail}{m.position_id ? ` · position ${m.position_id.slice(0, 8)}` : ''}
                </li>
              ))}
            </ul>
          )}
          {last.gaps.length === 0 ? (
            <p>No observation gap longer than 45 seconds.</p>
          ) : (
            <div className={styles.scroll}>
              <table className={styles.gaps}>
                <caption>Observation gaps, reported and never filled</caption>
                <thead>
                  <tr><th scope="col">Symbol</th><th scope="col">Started</th><th scope="col">Ended</th><th scope="col">Length</th></tr>
                </thead>
                <tbody>
                  {last.gaps.map((gap) => (
                    <tr key={`${gap.position_id}-${gap.started_at}`}>
                      <td>{gap.symbol}</td>
                      <td>{utcStamp(gap.started_at)}</td>
                      <td>{gap.ongoing ? 'Not observed since' : utcStamp(gap.ended_at)}</td>
                      <td>{gap.ongoing ? 'ongoing' : ageText(gap.seconds)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
      {data && <p className={styles.note}>{data.note}</p>}
    </div>
  )
}
