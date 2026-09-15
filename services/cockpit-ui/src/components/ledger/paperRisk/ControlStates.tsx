import type { RiskState } from '../../../api/paperRiskTypes'
import { utcStamp } from './paperRiskFormat'
import styles from './ControlStates.module.css'

/** The persistent entry pause and the kill switch as stored, with who changed them last and why. */
export function ControlStates({ risk }: { risk: RiskState }) {
  const pause = risk.pause
  const kill = risk.kill_switch
  const paused = pause?.entries_paused !== false
  const killed = kill?.active !== false
  const lastPause = pause?.recent[0]
  return (
    <div className={styles.states}>
      <div className={`${styles.card} ${paused ? styles.warn : styles.good}`}>
        <span>Entry pause</span>
        <strong>{pause ? (paused ? 'Paused' : 'Not paused') : 'Unavailable'}</strong>
        <p>{pause ? `${pause.reason} · ${utcStamp(pause.updated_at)}` : 'Pause state unavailable, so new entries are refused.'}</p>
        {lastPause && <p>Last change by {lastPause.operator} at {utcStamp(lastPause.created_at)}.</p>}
        <p>Pausing stops new paper entries only. Open positions keep their observations and exits.</p>
      </div>
      <div className={`${styles.card} ${killed ? styles.bad : styles.good}`}>
        <span>Kill switch</span>
        <strong>{kill ? (killed ? 'Engaged' : 'Not engaged') : 'Unavailable'}</strong>
        <p>{kill ? `${kill.reason} · by ${kill.operator} · ${utcStamp(kill.changed_at)}` : 'Kill switch state unavailable, so new entries are refused.'}</p>
        {kill?.active && kill.pending_closes.length > 0 && (
          <p className="tone-warn">
            Waiting for a fresh quote to close: {kill.pending_closes.map((p) => `${p.symbol} (${p.reason})`).join(', ')}. Retried every 15 seconds; no price is assumed.
          </p>
        )}
        <p>The kill switch stops new entries and closes every open paper position at its next observed quote.</p>
      </div>
    </div>
  )
}
