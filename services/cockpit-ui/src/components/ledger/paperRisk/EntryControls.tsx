import { useState } from 'react'
import type { usePaperRiskActions } from '../../../api/hooks/usePaperRisk'
import type { RiskState } from '../../../api/paperRiskTypes'
import { ConfirmDialog } from './ConfirmDialog'
import { rememberOperator, rememberedOperator } from './paperRiskOperator'
import styles from './EntryControls.module.css'

type Actions = ReturnType<typeof usePaperRiskActions>
type Change = 'pause' | 'resume' | 'kill' | 'resume-kill'

const COPY: Record<Change, { title: string; body: string; confirmLabel: string; phrase?: string; danger?: boolean }> = {
  pause: {
    title: 'Pause new paper entries?',
    body: 'New paper entries stop. Open paper positions keep their observations, stops, targets and closes.',
    confirmLabel: 'Pause entries',
  },
  resume: {
    title: 'Resume new paper entries?',
    body: 'Entries are admitted only where the kill switch, reconciliation and every limit also admit them. No real order is ever placed.',
    confirmLabel: 'Resume entries',
  },
  kill: {
    title: 'Engage the kill switch?',
    body: 'New paper entries stop and every open paper position closes at its next observed quote with reason kill switch. Closed positions stay closed.',
    confirmLabel: 'Engage kill switch',
    phrase: 'KILL',
    danger: true,
  },
  'resume-kill': {
    title: 'Resume after the kill switch?',
    body: 'The kill switch clears only when no paper position is still open. New paper entries stay paused until you resume them separately.',
    confirmLabel: 'Clear kill switch',
    phrase: 'RESUME',
    danger: true,
  },
}

/** Pause, resume, kill and resume after a kill, each with the operator's name, a reason and a confirmation. */
export function EntryControls({ risk, actions }: { risk: RiskState; actions: Actions }) {
  const [operator, setOperator] = useState(rememberedOperator)
  const [reason, setReason] = useState('')
  const [change, setChange] = useState<Change | null>(null)
  const paused = risk.pause?.entries_paused !== false
  const killed = risk.kill_switch?.active === true
  const valid = operator.trim().length > 0 && reason.trim().length >= 5
  const busy = actions.pause.isPending || actions.kill.isPending || actions.resume.isPending
  const failed = [actions.pause, actions.kill, actions.resume].find((mutation) => mutation.isError)?.error

  const confirm = () => {
    if (!change) return
    const body = { operator: operator.trim(), reason: reason.trim() }
    const done = { onSuccess: () => setReason('') }
    rememberOperator(body.operator)
    ;[actions.pause, actions.kill, actions.resume].forEach((mutation) => mutation.reset())
    if (change === 'kill') actions.kill.mutate(body, done)
    else if (change === 'resume-kill') actions.resume.mutate(body, done)
    else actions.pause.mutate({ ...body, entries_paused: change === 'pause' }, done)
    setChange(null)
  }

  const kill = actions.kill.data
  return (
    <div className={styles.controls}>
      <div className={styles.fields}>
        <label>
          Operator
          <input value={operator} maxLength={80} autoComplete="name" onChange={(event) => setOperator(event.target.value)} />
        </label>
        <label>
          Reason
          <input value={reason} maxLength={240} placeholder="Why this change is being made (5 characters or more)" onChange={(event) => setReason(event.target.value)} />
        </label>
      </div>
      <div className={styles.buttons}>
        {killed ? (
          <button type="button" className={`chip ${styles.danger}`} disabled={!valid || busy} onClick={() => setChange('resume-kill')}>
            Resume after kill switch
          </button>
        ) : (
          <>
            <button type="button" className="chip" disabled={!valid || busy} onClick={() => setChange(paused ? 'resume' : 'pause')}>
              {paused ? 'Resume new paper entries' : 'Pause new paper entries'}
            </button>
            <button type="button" className={`chip ${styles.danger}`} disabled={!valid || busy} onClick={() => setChange('kill')}>
              Engage kill switch
            </button>
          </>
        )}
      </div>
      {!valid && <p className={styles.hint}>Enter your name and a reason to enable these controls. Every change is recorded with both.</p>}
      {busy && <p role="status">Sending the change…</p>}
      {failed && <p role="alert" className="tone-bad">{failed.message}</p>}
      {kill && (
        <p role="status">
          Kill switch engaged. {kill.closed.length} paper position(s) closed at observed quotes; {kill.pending.length} waiting for a fresh quote.
        </p>
      )}
      {actions.pause.isSuccess && <p role="status">Entry pause updated and recorded.</p>}
      {actions.resume.isSuccess && <p role="status">Kill switch cleared. New paper entries stay paused until resumed.</p>}
      {change && <ConfirmDialog {...COPY[change]} busy={busy} onConfirm={confirm} onCancel={() => setChange(null)} />}
    </div>
  )
}
