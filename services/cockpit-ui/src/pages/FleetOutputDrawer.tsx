import { useEffect, useState } from 'react'
import { useFleetJobOutputs, useFleetOutput } from '../api/hooks/useFleetActivity'
import type { FleetJob } from '../api/types'
import { bytes, outputDelivery, when } from './fleetActivityText'
import styles from './FleetOutputDrawer.module.css'

/**
 * A job's stored output in a side drawer, as the output bridge stored it: the
 * newest by default, with the job's recent outputs to switch between. The state
 * API masks anything shaped like a token, key or webhook and says how many; it
 * adds nothing to the text.
 */
export function FleetOutputDrawer({ job, onClose }: { job: FleetJob; onClose: () => void }) {
  const outputs = useFleetJobOutputs(job.job_id)
  const [selected, setSelected] = useState<string | null>(null)
  const current = selected ?? outputs.data?.outputs[0]?.id ?? null
  const output = useFleetOutput(current)
  const data = output.data

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className={styles.backdrop} onClick={onClose}>
      <aside className={styles.drawer} role="dialog" aria-modal="true" aria-labelledby={`output-title-${job.job_id}`} onClick={(event) => event.stopPropagation()}>
        <header className={styles.head}>
          <div>
            <h3 id={`output-title-${job.job_id}`}>{job.name}: stored output</h3>
            <p>{data ? `stored ${when(data.received_at)} · written ${when(data.observed_at)} · ${bytes(data.bytes)}, ${data.lines} lines · ${outputDelivery(data)}` : 'reading…'}</p>
          </div>
          <button type="button" className="chip" onClick={onClose}>close</button>
        </header>
        {outputs.data && outputs.data.outputs.length > 1 && (
          <div className={styles.list} role="group" aria-label="Recent stored outputs">
            {outputs.data.outputs.map((item) => (
              <button key={item.id} type="button" className={item.id === current ? 'chip chip--active' : 'chip'} aria-pressed={item.id === current}
                onClick={() => setSelected(item.id)}>
                {when(item.received_at)}
              </button>
            ))}
          </div>
        )}
        {outputs.isError && <p className={`${styles.message} tone-bad`}>{(outputs.error as Error).message}</p>}
        {output.isError && <p className={`${styles.message} tone-bad`}>{(output.error as Error).message}</p>}
        {outputs.data?.outputs_unavailable && <p className={`${styles.message} tone-warn`}>{outputs.data.outputs_unavailable}</p>}
        {outputs.data && !current && <p className={`${styles.message} tone-dim`}>No stored output since {when(outputs.data.indexed_since)}. Silent runs are not stored.</p>}
        {data && (
          <>
            {data.masked > 0 && <p className={`${styles.message} tone-warn`}>{data.masked} token-, key- or webhook-shaped string{data.masked === 1 ? ' was' : 's were'} masked.</p>}
            {!data.accepted && <p className={`${styles.message} tone-warn`}>Refused at intake: {data.refused_because.join(', ') || 'no reason recorded'}.</p>}
            {data.truncated && <p className={`${styles.message} tone-dim`}>The output bridge cut this output to the intake bound before storing it.</p>}
            <pre className={styles.text}>{data.text}</pre>
            <p className={styles.note}>{data.note}</p>
          </>
        )}
      </aside>
    </div>
  )
}
