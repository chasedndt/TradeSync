import { useState } from 'react'
import { useFleetActivity } from '../api/hooks/useFleetActivity'
import type { FleetJob } from '../api/types'
import { FleetOutputDrawer } from './FleetOutputDrawer'
import { bytes, duration, elapsedSeconds, fireLine, laterRunsLine, outputDelivery, runTone, span, when } from './fleetActivityText'
import styles from './FleetJobActivity.module.css'

/**
 * One job's run progress and output, inside its expanded row: what is running
 * now and for how long, the last runs with status, duration and error, and the
 * latest stored output with where it went, its first lines and a drawer holding
 * the full text. Runs are the bridge's snapshot, so the snapshot time is shown.
 */
export function FleetJobActivity({ job }: { job: FleetJob }) {
  const activity = useFleetActivity()
  const [reading, setReading] = useState(false)
  if (activity.isError) return <p className="tone-bad">Run progress unavailable: {(activity.error as Error).message}</p>
  if (!activity.data) return <p className="tone-dim">Reading runs and outputs…</p>

  const now = Date.now()
  const { snapshot, jobs, outputs_indexed_since: indexedSince } = activity.data
  const mine = jobs[job.job_id]
  const output = mine?.latest_output ?? null
  const later = mine ? laterRunsLine(mine) : null

  return (
    <div className={styles.activity}>
      <section aria-label={`What ${job.name} is running now`}>
        <h4>Running now</h4>
        {mine?.running.length ? mine.running.map((run) => (
          <p key={run.id} className={styles.running}>
            {run.status ?? 'running'} for {span(elapsedSeconds(run, now))} · since {when(run.started_at ?? run.claimed_at)}
            {run.in_latest_snapshot === false && <span className="tone-warn"> · absent from the newest run snapshot, so it may have finished</span>}
          </p>
        )) : <p className="tone-dim">Nothing running in the run snapshot of {when(snapshot.runs_snapshot_at)}.</p>}
        <p className={styles.meta}>
          Run snapshot {when(snapshot.runs_snapshot_at)}, {span(snapshot.runs_snapshot_age_s)} old · the fleet bridge posts every {span(snapshot.bridge_every_s.fleet)}
        </p>
      </section>

      <section aria-label={`Last runs of ${job.name}`}>
        <h4>Last runs</h4>
        {mine?.runs.length ? (
          <table className={styles.runs}>
            <thead><tr><th>started</th><th>status</th><th>duration</th><th>error</th></tr></thead>
            <tbody>
              {mine.runs.map((run) => (
                <tr key={run.id}>
                  <td className={styles.mono}>{when(run.started_at ?? run.claimed_at)}</td>
                  <td className={`${styles.mono} ${run.running ? styles.running : runTone(run.status)}`}>
                    {run.running ? `running ${span(elapsedSeconds(run, now))}` : run.status ?? '—'}
                  </td>
                  <td className={styles.mono}>{run.running ? '—' : duration(run.duration_ms)}</td>
                  <td><div className={styles.error}>{run.error ?? ''}</div></td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <p className="tone-dim">No runs of this job in the run snapshot.</p>}
      </section>

      <section aria-label={`Latest output of ${job.name}`}>
        <h4>Latest output</h4>
        {output ? (
          <>
            <p className={styles.meta}>
              Stored {when(output.received_at)} · written {when(output.observed_at)}{output.ran_at_stamp ? ` (fleet host clock ${output.ran_at_stamp})` : ''}
              {' '}· {bytes(output.bytes)}, {output.lines} lines{output.truncated ? ', cut to the intake bound' : ''} · {outputDelivery(output)}
            </p>
            {!output.accepted && <p className="tone-warn">Refused at intake: {output.refused_because.join(', ') || 'no reason recorded'}.</p>}
            <p className={styles.meta}>Latest model call {when(mine?.latest_fire?.ts)}: {fireLine(mine?.latest_fire ?? null)}</p>
            {job.last_delivery_error && <p className="tone-warn">Last delivery error: {job.last_delivery_error.slice(0, 300)}</p>}
            {later && <p className="tone-dim">{later}</p>}
            <pre className={styles.head}>{output.first_lines.join('\n')}</pre>
            <button type="button" className="chip" onClick={() => setReading(true)}>read the full output</button>
          </>
        ) : (
          <>
            <p className="tone-dim">No stored output since {when(indexedSince)}. Silent runs are not stored.</p>
            {job.last_delivery_error && <p className="tone-warn">Last delivery error: {job.last_delivery_error.slice(0, 300)}</p>}
          </>
        )}
        <p className={styles.meta}>
          Newest output stored {when(snapshot.outputs_received_at)} · the output bridge posts every {span(snapshot.bridge_every_s.outputs)}
        </p>
      </section>
      {reading && <FleetOutputDrawer job={job} onClose={() => setReading(false)} />}
    </div>
  )
}
