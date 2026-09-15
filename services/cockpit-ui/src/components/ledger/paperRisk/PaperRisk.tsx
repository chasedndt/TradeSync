import { usePaperAccount, usePaperReconciliation, usePaperRiskActions, usePaperRiskState } from '../../../api/hooks/usePaperRisk'
import { AccountFigures } from './AccountFigures'
import { ControlStates } from './ControlStates'
import { EntryControls } from './EntryControls'
import { LimitMeters } from './LimitMeters'
import { LimitsEditor } from './LimitsEditor'
import { ReconciliationSummary } from './ReconciliationSummary'
import { codeLabel, utcStamp } from './paperRiskFormat'
import styles from './PaperRisk.module.css'

/** The paper account, its limits, the entry pause and kill switch, and the last restart reconciliation. Paper only. */
export function PaperRisk() {
  const risk = usePaperRiskState()
  const account = usePaperAccount()
  const reconciliation = usePaperReconciliation()
  const actions = usePaperRiskActions()
  const r = risk.data
  const refreshing = risk.isFetching || account.isFetching || reconciliation.isFetching

  return (
    <section className={`panel ${styles.panel}`} aria-labelledby="paper-risk-title">
      <header className={styles.header}>
        <div>
          <h3 id="paper-risk-title">Paper risk</h3>
          <p>Paper account, entry limits, pause and kill switch. Limits refuse new paper entries; nothing here places an order or holds a wallet.</p>
        </div>
        <div className={styles.reading}>
          <span>Reading {r ? utcStamp(r.as_of) : '—'}</span>
          <button type="button" className="chip" disabled={refreshing} onClick={() => void actions.refresh()}>
            {refreshing ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </header>

      {risk.isLoading && <p>Loading paper risk state…</p>}
      {risk.isError && <p role="alert" className="tone-bad">Paper risk state unavailable: {risk.error.message}. New entries are refused while it is unknown.</p>}
      {r && (
        <div className={`${styles.verdict} ${r.entries_allowed ? styles.allowed : styles.blocked}`} role="status">
          <strong>{r.entries_allowed ? 'Standing checks admit new paper entries' : 'New paper entries are refused'}</strong>
          {r.blocking.length > 0 && (
            <ul>
              {r.blocking.map((block) => (
                <li key={`${block.code}-${block.message}`}><span>{codeLabel(block.code)}:</span> {block.message}</li>
              ))}
            </ul>
          )}
          <p>{r.entries_note}</p>
        </div>
      )}
      {r && <ControlStates risk={r} />}
      {r && <EntryControls risk={r} actions={actions} />}
      <AccountFigures account={account} limits={r?.limits?.values} />
      {r && <LimitMeters risk={r} />}
      <ReconciliationSummary reconciliation={reconciliation} />
      {r?.limits && <LimitsEditor limits={r.limits} mutation={actions.limits} />}
      {r && <p className={styles.note}>{r.note}</p>}
    </section>
  )
}
