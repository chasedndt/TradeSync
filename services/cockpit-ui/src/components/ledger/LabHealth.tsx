import { Link } from 'react-router-dom'
import type { LabHealthResponse, LabJob } from '../../api/strikezoneTypes'
import { humanize, minutesAgo, since } from './format'
import styles from './LabHealth.module.css'

/** The lab's integrity checks, its jobs with the reason each one failed, and the fleet inspector's standing issues. */
export function LabHealth({ data }: { data: LabHealthResponse }) {
  const state = data.ok === true ? 'OK' : data.ok === false ? 'HOLD' : 'NO REPORT'
  const tone = data.ok === true ? 'tone-good' : data.ok === false ? 'tone-warn' : 'tone-dim'
  const counts = data.counts

  return (
    <section className="panel" id="lab-health">
      <div className={`panel-heading ${styles.heading}`}>
        <div>
          <h3>Lab health</h3>
          <p>integrity watchdog checked {minutesAgo(data.checked_age_minutes)} · bridge delivered {minutesAgo(data.bridge_age_minutes)} · last call {minutesAgo(data.last_signal_age_minutes)}</p>
        </div>
        <span className={`${styles.state} ${tone}`}>{state}</span>
      </div>
      <div className={styles.body}>
        {data.issues.length > 0 && (
          <ul className={styles.issues}>
            {data.issues.map((issue) => <li key={issue.code}><b>{humanize(issue.code)}</b>{issue.text}</li>)}
          </ul>
        )}
        {data.ok === true && <p className="tone-good">No integrity issues across {counts.signal_records.toLocaleString()} calls and {counts.resolved_outcomes} outcomes.</p>}
        {data.ok === false && (
          <p className={styles.hold}>
            While the hold stands, automatic paper evaluation stays fail-closed. Checked: {counts.signal_records.toLocaleString()} calls,
            {' '}{counts.paper_candidates} paper trades, {counts.resolved_outcomes} resolved.
          </p>
        )}
      </div>
      <div className={styles.scroll}>
        <table className={styles.table}>
          <thead><tr><th>job</th><th>schedule</th><th>last run</th><th>runs 24h</th><th>why it failed</th></tr></thead>
          <tbody>{data.jobs.map((job) => <JobLine key={job.job_id} job={job} />)}</tbody>
        </table>
      </div>
      {data.fleet && (
        <details className={styles.fleet}>
          <summary>
            Fleet inspector: {data.fleet.issue_count} standing issues, unchanged since {data.fleet.unchanged_since ? new Date(data.fleet.unchanged_since).toUTCString().slice(5, 16) : '—'}
            {' '}· {data.fleet.strikezone_issue_names.length} involve StrikeZone
          </summary>
          <div className={styles.names}>
            <div><h4>StrikeZone</h4><ul>{data.fleet.strikezone_issue_names.map((n) => <li key={n}>{n}</li>)}</ul></div>
            <div><h4>Elsewhere in the fleet</h4><ul>{data.fleet.other_issue_names.map((n) => <li key={n}>{n}</li>)}</ul></div>
          </div>
        </details>
      )}
      <p className={styles.foot}>Enable, disable or reschedule these jobs on <Link to="/agents">Hermes &amp; agents</Link> or <Link to="/fleet">Fleet</Link>.</p>
    </section>
  )
}

function JobLine({ job }: { job: LabJob }) {
  const failing = job.last_status === 'error' || job.last_status === 'failed'
  const statusTone = failing ? 'tone-bad' : job.last_status === 'ok' ? 'tone-good' : 'tone-dim'
  return (
    <tr>
      <td className={job.enabled ? undefined : 'tone-dim'}>{job.name}{job.enabled ? '' : ' · disabled'}</td>
      <td className={styles.mono}>{job.schedule_display || '—'}</td>
      <td className={`${styles.mono} ${statusTone}`}>
        {job.last_status ?? '—'} · {since(job.last_run_at)}{job.overdue && <span className="tone-warn"> · overdue</span>}
      </td>
      <td className={styles.mono}>{job.runs_24h}{job.failed_24h > 0 && <span className="tone-bad"> ({job.failed_24h} failed)</span>}</td>
      <td className={styles.why}>
        {job.diagnosis && <span className="tone-bad" title={job.error_excerpt ?? undefined}>{job.diagnosis}</span>}
        {job.delivery_problem && <span className="tone-warn">Delivery: {job.delivery_problem}</span>}
        {!job.diagnosis && !job.delivery_problem && <span className="tone-dim">—</span>}
      </td>
    </tr>
  )
}
