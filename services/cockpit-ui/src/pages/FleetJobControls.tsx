import { useState } from 'react'
import { useFleetDirective, type FleetDirectiveBody } from '../api/hooks/useFleet'
import type { FleetJob, FleetSchedule } from '../api/types'
import styles from './FleetJobControls.module.css'

/**
 * The controls for one Hermes job. Each sends a directive the state API applies
 * through the Hermes gateway's jobs API at once; a working-directory change, or
 * anything while the gateway is down, waits for the host bridge. Running a job
 * or moving its delivery asks first, because both can reach Discord.
 */
export function FleetJobControls({ job, presets }: { job: FleetJob; presets: Record<string, FleetSchedule> }) {
  const directive = useFleetDirective()
  const [preset, setPreset] = useState('')
  const paused = job.state === 'paused'
  const discord = job.deliver.startsWith('discord:')
  const pendingEnabled = job.pending_directives.some((d) => d.kind === 'set_enabled')
  const busy = directive.isPending

  const send = (body: Omit<FleetDirectiveBody, 'job_id'>, question?: string) => {
    if (question && !window.confirm(question)) return
    directive.mutate({ job_id: job.job_id, ...body })
  }
  const result = directive.data
  const error = directive.error as Error | null

  return (
    <div className={styles.controls}>
      <div className={styles.row}>
        <select className={styles.select} value={preset} onChange={(e) => setPreset(e.target.value)} aria-label={`schedule for ${job.name}`}>
          <option value="">schedule…</option>
          {Object.entries(presets).map(([k, v]) => <option key={k} value={k}>{v.display}</option>)}
        </select>
        <button type="button" className="chip" disabled={!preset || busy} onClick={() => { send({ kind: 'set_schedule', preset }); setPreset('') }}>set</button>
        <button type="button" className="chip" disabled={busy || pendingEnabled} onClick={() => send({ kind: 'set_enabled', enabled: !job.enabled })}>
          {pendingEnabled ? 'pending' : job.enabled ? 'disable' : 'enable'}
        </button>
        <button type="button" className="chip" disabled={busy || !job.enabled} onClick={() => send({ kind: paused ? 'resume' : 'pause' })}>
          {paused ? 'resume' : 'pause'}
        </button>
        <button type="button" className="chip" disabled={busy || !job.enabled}
          onClick={() => send({ kind: 'run_now' }, `Run "${job.name}" now?${discord ? ' It delivers to Discord.' : ''}`)}>
          run now
        </button>
        {discord && (
          <button type="button" className="chip" disabled={busy}
            onClick={() => send({ kind: 'set_deliver', deliver: 'local' },
              `Stop delivering "${job.name}" to Discord? Its output stays in TradeSync, and the Discord target is kept so it can be restored.`)}>
            TradeSync only
          </button>
        )}
        {!discord && job.restorable_deliver && (
          <button type="button" className="chip" disabled={busy}
            onClick={() => send({ kind: 'set_deliver', deliver: job.restorable_deliver ?? 'local' }, `Deliver "${job.name}" to Discord again?`)}>
            restore Discord
          </button>
        )}
      </div>
      {busy && <div className={styles.note}>sending…</div>}
      {result && !busy && (
        <div className={`${styles.note} ${result.status === 'applied' ? 'tone-good' : 'tone-warn'}`}>
          {result.status === 'applied' ? `applied by the gateway: ${result.detail}` : `pending for the host bridge${result.detail ? `: ${result.detail}` : ''}`}
        </div>
      )}
      {error && !busy && <div className={`${styles.note} tone-bad`}>{error.message}</div>}
    </div>
  )
}
