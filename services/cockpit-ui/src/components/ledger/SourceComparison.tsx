import { useQuery } from '@tanstack/react-query'
import { apiGet } from '../../api/client'
import styles from './TradeResearch.module.css'

type Result = { eligible: number; context_available: number; selected: number; abstained: number; baseline_mean_bps_per_opportunity: number | null; filter_mean_bps_per_opportunity: number | null; paired_mean_difference_bps: number | null; excluded: Record<string, number>; note: string }
type Comparison = { summary: Result; cohorts: (Result & { style: string })[]; records_considered: number; truncated: boolean; scope: string }
const value = (n: number | null) => n == null ? 'Not measured' : `${n.toLocaleString(undefined, { maximumFractionDigits: 2 })} bps`

export function SourceComparison() {
  const query = useQuery({ queryKey: ['paper-source-comparison'], queryFn: () => apiGet<Comparison>('/state/paper-positions/source-comparison'), refetchInterval: 30000 })
  const data = query.data
  return <section className={`panel ${styles.panel}`} aria-labelledby="source-comparison-title">
    <h3 id="source-comparison-title">Does liquidity context help?</h3>
    <p>Retrospective research only. Compare every eligible paper entry with a hypothetical filter that trades only when the frozen book aligns with its direction. No strategy weights change.</p>
    {query.isLoading && <p>Loading source comparison…</p>}
    {query.isError && <p role="alert">Source comparison unavailable. No result substituted.</p>}
    {data?.summary && <>
      {data.summary.eligible === 0 && <p>No clean closed managed-paper trades to compare yet. This is not a zero-return result.</p>}
      <div className={styles.scroll}><table><thead><tr><th>Holding style</th><th>Eligible entries</th><th>Context available</th><th>Selected / skipped</th><th>Baseline mean</th><th>Filter mean</th><th>Paired difference</th></tr></thead>
        <tbody>{data.cohorts.map(c => <tr key={c.style}><td>{c.style}</td><td>{c.eligible}</td><td>{c.context_available} / {c.eligible}</td><td>{c.selected} / {c.abstained}</td><td>{value(c.baseline_mean_bps_per_opportunity)}</td><td>{value(c.filter_mean_bps_per_opportunity)}</td><td>{value(c.paired_mean_difference_bps)}</td></tr>)}</tbody></table></div>
      <p>Both means divide by the same original eligible entry count; skipped entries contribute zero to the filter. 1 basis point (bps) = 0.01%. These are net simulated returns per opportunity, not account returns.</p>
      <details><summary>Rule, exclusions and limits</summary>
        <p>Book alignment = (bid notional − ask notional) / (bid notional + ask notional), with sign reversed for shorts. Fixed experimental threshold: 0.2. Missing context skips a trade; it is not neutral evidence. Only a frozen sample no older than 30 seconds is used.</p>
        <p>Excluded: {Object.entries(data.summary.excluded).map(([reason, count]) => `${reason.replace(/_/g, ' ')}: ${count}`).join(' · ') || 'none in this record window'}.</p>
        <p>{data.records_considered} records considered · {data.truncated ? 'latest 1,000 only' : 'not truncated'}. {data.scope}</p>
        <p>{data.summary.note}</p>
      </details>
    </>}
  </section>
}
