import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPost } from '../../api/client'
import styles from './TradeResearch.module.css'

type Trial = { id: string; registered_at: string; specification_sha256: string; specification: { style: string; [key: string]: unknown } }
type Evaluation = { state: string; pending_outcomes?: number; outside_population?: number; comparison?: { eligible: number; context_available: number; paired_mean_difference_bps: number | null }; note: string }
function TrialRow({ trial }: { trial: Trial }) {
  const [inspect, setInspect] = useState(false)
  const evaluation = useQuery({ queryKey: ['trial-evaluation', trial.id], queryFn: () => apiGet<Evaluation>(`/state/research-trials/${trial.id}/evaluation`), enabled: inspect, refetchInterval: inspect ? 30000 : false })
  const result = evaluation.data
  return <details className={styles.run} onToggle={event => setInspect(event.currentTarget.open)}>
    <summary>{trial.specification.style} · registered {new Date(trial.registered_at).toLocaleString()}</summary>
    <p>Specification fingerprint: {trial.specification_sha256}</p>
    {evaluation.isLoading && <p>Checking forward cohort…</p>}
    {evaluation.isError && <p role="alert">Evaluation unavailable: {evaluation.error.message}</p>}
    {result && <>
      <p>State: {result.state.replace(/_/g, ' ')} · pending outcomes: {result.pending_outcomes ?? 'unknown'}.</p>
      {result.comparison && <p>Clean eligible entries: {result.comparison.eligible} · with context: {result.comparison.context_available} · paired difference: {result.comparison.paired_mean_difference_bps == null ? 'not measured' : `${result.comparison.paired_mean_difference_bps.toFixed(2)} bps per original opportunity`}.</p>}
      <p>{result.note}</p>
    </>}
    <details><summary>Frozen specification</summary><pre style={{ overflow: 'auto', maxHeight: 320 }}>{JSON.stringify(trial.specification, null, 2)}</pre></details>
  </details>
}

export function ResearchTrials() {
  const qc = useQueryClient()
  const trials = useQuery({ queryKey: ['research-trials'], queryFn: () => apiGet<{ trials: Trial[]; note: string }>('/state/research-trials'), refetchInterval: 30000 })
  const [style, setStyle] = useState('scalp')
  const register = useMutation({ mutationFn: () => apiPost<{ duplicate: boolean }>('/state/research-trials', { style }), onSuccess: () => qc.invalidateQueries({ queryKey: ['research-trials'] }) })
  return <section className={`panel ${styles.panel}`} aria-labelledby="research-trials-title">
    <h3 id="research-trials-title">Registered forward research</h3>
    <p>Freeze the existing liquidity-filter protocol before later paper entries. Registration does not generate opportunities, schedule jobs, open positions or change weights.</p>
    <p>30-day entry window; review after outcomes resolve. The 100-clean-entry floor is an operational review threshold, not proof of significance. Existing operator-selected trades are not a randomized experiment.</p>
    <form className={styles.controls} onSubmit={event => { event.preventDefault(); if (window.confirm(`Register the fixed ${style} liquidity-filter research protocol now? The specification and timestamp cannot be edited. No trade or job will start; registering the same protocol again keeps its original timestamp.`)) register.mutate() }}>
      <label>Trial holding style<select value={style} onChange={event => { setStyle(event.target.value); register.reset() }}><option value="scalp">Scalp</option><option value="intraday">Intraday</option><option value="swing">Swing</option></select></label>
      <button className="chip" disabled={register.isPending || trials.isError}>{register.isPending ? 'Registering…' : 'Register fixed research protocol'}</button>
    </form>
    {register.isError && <p role="alert">Registration failed: {register.error.message}</p>}
    {register.isSuccess && <p role="status">{register.data.duplicate ? 'Existing registration retained; timestamp unchanged.' : 'Protocol registered. No trade or job started.'}</p>}
    {trials.isLoading && <p>Loading trial registry…</p>}
    {trials.isError && <p role="alert">Trial registry unavailable.</p>}
    {trials.data?.trials.length === 0 && <p>No registered trials yet. Retrospective comparisons are separate.</p>}
    {trials.data?.trials.map(trial => <TrialRow key={trial.id} trial={trial} />)}
  </section>
}
