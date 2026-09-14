import { useState } from 'react'
import type { FleetJob, FleetSchedule } from '../api/types'
import { FleetJobControls } from './FleetJobControls'
import styles from './Fleet.module.css'

const fmtTokens = (n: number) => (n >= 1_000_000 ? `${(n / 1_000_000).toFixed(1)}M` : n >= 1000 ? `${Math.round(n / 1000)}k` : String(n))
const ago = (iso: string | null) => {
  if (!iso) return '—'
  const m = Math.round((Date.now() - new Date(iso).getTime()) / 60_000)
  return m < 60 ? `${m}m ago` : m < 1440 ? `${Math.round(m / 60)}h ago` : `${Math.round(m / 1440)}d ago`
}

/** One fleet job: what it is, when it runs, what it costs, its last error, and its controls. */
export function FleetJobRow({ job, presets }: { job: FleetJob; presets: Record<string, FleetSchedule> }) {
  const [open, setOpen] = useState(false)
  const pendingSchedule = job.pending_directives.find((d) => d.kind === 'set_schedule')
  const statusTone = job.last_status === 'error' || job.last_status === 'failed' ? 'tone-bad' : job.last_status === 'ok' || job.last_status === 'completed' ? 'tone-good' : 'tone-dim'

  return (
    <>
      <tr>
        <td>
          <button type="button" className={styles.name} style={{ background: 'none', border: 0, color: 'inherit', padding: 0, cursor: 'pointer', textAlign: 'left' }} onClick={() => setOpen(!open)}>
            {job.name}
          </button>
          <div className={styles.desc}>{open ? job.description || 'no description' : (job.description || 'no description').slice(0, 140)}{!open && job.description.length > 140 ? '…' : ''}</div>
        </td>
        <td className={styles.mono}>
          {job.schedule_display || '—'}
          {job.state === 'paused' && <div className="tone-warn">paused</div>}
          {pendingSchedule && <div className={styles.pending}>→ {String((pendingSchedule.payload as { preset?: string }).preset)} pending</div>}
        </td>
        <td className={styles.mono}>{job.no_agent ? 'script' : job.model || 'agent'}</td>
        <td className={styles.mono}>{job.deliver.startsWith('discord:') ? 'discord' : job.deliver === 'local' ? 'TradeSync only' : job.deliver}</td>
        <td className={`${styles.mono} ${statusTone}`} title={job.next_run_at ? `next ${new Date(job.next_run_at).toUTCString()}` : ''}>
          {job.last_status || '—'} · {ago(job.last_run_at)}
          <div className="tone-dim">{job.state_source ?? 'bridge'}{job.gateway_missing ? ' · absent from gateway' : ''}</div>
        </td>
        <td className={styles.mono}>{job.runs_24h}{job.failed_24h > 0 ? <span className="tone-bad"> ({job.failed_24h} failed)</span> : ''}</td>
        <td className={styles.mono}>{fmtTokens(job.tokens_24h)} / {fmtTokens(job.tokens_7d)}</td>
        <td><FleetJobControls job={job} presets={presets} /></td>
      </tr>
      {open && (
        <tr>
          <td colSpan={8} style={{ background: 'rgba(255,255,255,0.015)' }}>
            <div className={styles.desc} style={{ maxWidth: 'none', display: 'grid', gap: 4 }}>
              <span>id {job.job_id} · script {job.script || '—'} · workdir {job.workdir || '—'} · state {job.state || '—'}</span>
              <span>next run {job.next_run_at ? new Date(job.next_run_at).toUTCString() : '—'} · snapshot {ago(job.snapshot_at)}</span>
              <span>{job.fires_7d} model calls in 7 days</span>
              {job.last_error && <span className="tone-bad" style={{ whiteSpace: 'pre-wrap' }}>last error: {job.last_error.slice(0, 600)}</span>}
              {job.last_delivery_error && <span className="tone-warn">last delivery error: {job.last_delivery_error.slice(0, 300)}</span>}
            </div>
          </td>
        </tr>
      )}
    </>
  )
}
