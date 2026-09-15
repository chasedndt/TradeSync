import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiGet } from '../../api/client'
import { PaperOpenForm } from './paper/PaperOpenForm'
import { PaperRow } from './paper/PaperRow'
import type { Portfolio } from './paper/paperTypes'
import styles from './ManagedPaper.module.css'

type Control = { entries_paused: boolean; reason: string; updated_at: string; note: string }

export function ManagedPaper() {
  const qc = useQueryClient()
  const control = useQuery({ queryKey: ['paper-control'], queryFn: () => apiGet<Control>('/state/paper-control'), refetchInterval: 5000 })
  const portfolio = useQuery({ queryKey: ['managed-paper'], queryFn: () => apiGet<Portfolio>('/state/paper-positions'), refetchInterval: 15000 })
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ['managed-paper'] })
    void qc.invalidateQueries({ queryKey: ['paper-candidates'] })
  }
  const now = Date.now()
  const worker = portfolio.data?.worker
  const healthy = worker?.last_tick != null && now / 1000 - worker.last_tick < 60 && !worker.last_error
  const entryAllowed = !control.isError && control.data?.entries_paused === false
  return <section className={`panel ${styles.panel}`} aria-labelledby="managed-paper-title">
    <h3 id="managed-paper-title">Managed paper positions</h3>
    <p>Operator-selected paper positions, separate from the historical StrikeZone ledger. No wallet, real order or automatic strategy promotion.</p>
    <p>Observer: {portfolio.isLoading ? 'checking…' : healthy ? 'running' : 'unavailable or stale'}{worker?.last_tick != null ? `, last pass ${new Date(worker.last_tick * 1000).toLocaleTimeString()}` : ''}{worker?.last_error ? ` · ${worker.last_error}` : ''}. Maximum three open positions, one per symbol.</p>
    <p>New paper entries: {control.isLoading ? 'checking control…' : control.isError ? 'disabled — control unavailable' : entryAllowed ? 'enabled' : 'paused'}. Existing observations and closes remain available.</p>
    {control.data && <p>Control reason: {control.data.reason} · updated {new Date(control.data.updated_at).toLocaleString()}.</p>}
    <p>Pause, resume and the kill switch are changed in Paper risk above, with your name and a reason; every change is recorded.</p>
    <PaperOpenForm entryAllowed={entryAllowed} healthy={healthy} onOpened={refresh} />
    {portfolio.isError && <p role="alert">Paper portfolio unavailable: {portfolio.error.message}</p>}
    {portfolio.data?.positions.length === 0 && <p>No managed paper positions yet. The empty portfolio is not a zero-return performance result.</p>}
    {portfolio.data?.positions.map(row => <PaperRow key={row.id} row={row} refresh={refresh} />)}
    {portfolio.data && <p className={styles.note}>{portfolio.data.note}</p>}
  </section>
}
