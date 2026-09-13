import { useMemo, useState } from 'react'
import { useFleetDirectives, useFleetJobs, useFleetUsage } from '../api/hooks/useFleet'
import { FleetJobRow } from './FleetJobRow'
import styles from './Fleet.module.css'

const fmtTokens = (n: number) => (n >= 1_000_000 ? `${(n / 1_000_000).toFixed(2)}M` : n >= 1000 ? `${Math.round(n / 1000)}k` : String(n))

/**
 * The Hermes fleet: every cron job with its description, cadence, delivery,
 * last result, run count and token usage, and its controls. Controls go
 * through the Hermes gateway's jobs API on its port and apply at once; the
 * host bridge edits the registry only for the working directory, or when the
 * gateway is down. Every change is recorded with what it replaced.
 */
export function Fleet() {
  const jobs = useFleetJobs()
  const usage = useFleetUsage(7)
  const directives = useFleetDirectives(20)
  const [query, setQuery] = useState('')
  const [onlyEnabled, setOnlyEnabled] = useState(true)

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase()
    return (jobs.data?.jobs ?? []).filter((j) => (!onlyEnabled || j.enabled) && (!q || `${j.name} ${j.description} ${j.job_id}`.toLowerCase().includes(q)))
  }, [jobs.data, query, onlyEnabled])

  const totals = useMemo(() => {
    const all = jobs.data?.jobs ?? []
    return {
      jobs: all.length, enabled: all.filter((j) => j.enabled).length,
      hot: all.filter((j) => j.enabled && j.schedule.kind === 'interval' && (j.schedule.minutes ?? 999) <= 15).length,
      runs24h: all.reduce((s, j) => s + j.runs_24h, 0), failed24h: all.reduce((s, j) => s + j.failed_24h, 0),
      tokens24h: all.reduce((s, j) => s + j.tokens_24h, 0), tokens7d: all.reduce((s, j) => s + j.tokens_7d, 0),
    }
  }, [jobs.data])

  const maxDay = Math.max(1, ...(usage.data?.daily ?? []).map((d) => d.total_tokens))

  return (
    <div className={styles.page}>
      <section className={`panel ${styles.hero}`}>
        <div>
          <div className={styles.kicker}>Hermes fleet · controls through the gateway's jobs API · read model from the host bridge</div>
          <h2>Every job, its cadence, and what it costs.</h2>
          <p>
            Schedule, enable, pause, run now and delivery changes go to the Hermes gateway's jobs API on its port and apply at once. The host bridge
            posts the registry, run ledger and token audit every five minutes, and edits the registry itself only for the working directory or while
            the gateway is down. Every change keeps the value it replaced, so it can be reversed.
          </p>
        </div>
        <div style={{ display: 'grid', gap: 4, justifyItems: 'end' }}>
          <span className={jobs.data?.control?.gateway_api && jobs.data.control.gateway_status === 'live' ? 'tone-good' : 'tone-warn'} style={{ fontSize: 11 }}>
            {jobs.data?.control ? (jobs.data.control.gateway_api ? `gateway jobs API · ${jobs.data.control.gateway_status}` : 'gateway jobs API not configured · bridge only') : '—'}
          </span>
          <span className="metric-sub">snapshot {jobs.data?.snapshot_at ? new Date(jobs.data.snapshot_at).toUTCString().slice(17, 25) : '—'} UTC</span>
        </div>
      </section>

      <div className={styles.stats}>
        <div className={styles.stat}><span>jobs</span><strong>{totals.enabled} / {totals.jobs}</strong></div>
        <div className={styles.stat}><span>≤15 min cadence</span><strong className={totals.hot > 0 ? 'tone-warn' : 'tone-good'}>{totals.hot}</strong></div>
        <div className={styles.stat}><span>runs 24h</span><strong>{totals.runs24h}{totals.failed24h > 0 ? <span className="tone-bad"> · {totals.failed24h} failed</span> : ''}</strong></div>
        <div className={styles.stat}><span>tokens 24h</span><strong>{fmtTokens(totals.tokens24h)}</strong></div>
        <div className={styles.stat}><span>tokens 7d</span><strong>{fmtTokens(totals.tokens7d)}</strong></div>
        <div className={styles.stat}><span>model calls 7d</span><strong>{usage.data?.daily.reduce((s, d) => s + d.fires, 0) ?? '—'}</strong></div>
      </div>

      <section className="panel">
        <div className="panel-heading"><div><h3>Token usage by day</h3><p>the fleet's own usage audit · model calls only; script jobs use no tokens · no price assumed</p></div></div>
        <div className={styles.bars}>
          {(usage.data?.daily ?? []).map((d) => (
            <div key={d.day} className={styles.bar} style={{ height: `${Math.max(2, (d.total_tokens / maxDay) * 70)}px` }} title={`${d.day}: ${d.total_tokens.toLocaleString()} tokens, ${d.fires} calls`}>
              <span>{d.day.slice(5)}</span>
            </div>
          ))}
        </div>
        <div style={{ padding: '18px 17px 4px', display: 'grid', gap: 4, fontSize: 11 }}>
          {(usage.data?.by_job ?? []).slice(0, 8).map((b) => (
            <div key={b.job_id} style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) auto auto', gap: 12 }}>
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{b.name}</span>
              <span className={styles.mono}>{b.fires} calls</span>
              <span className={styles.mono}>{fmtTokens(b.total_tokens)} · avg {fmtTokens(b.avg_tokens)}</span>
            </div>
          ))}
        </div>
        <p className={styles.foot}>{usage.data?.note}</p>
      </section>

      <section className="panel">
        <div className={styles.toolbar}>
          <button type="button" className={onlyEnabled ? 'chip chip--active' : 'chip'} onClick={() => setOnlyEnabled(!onlyEnabled)} aria-pressed={onlyEnabled}>enabled only</button>
          <span className="metric-sub">{rows.length} shown</span>
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="filter jobs…" aria-label="Filter jobs" />
        </div>
        {jobs.isError && <p className="tone-bad" style={{ padding: 16 }}>Fleet read model unavailable.</p>}
        {jobs.data && jobs.data.jobs.length === 0 && <p className="tone-dim" style={{ padding: 16 }}>No snapshot yet. The host bridge posts one every five minutes.</p>}
        <div style={{ overflowX: 'auto' }}>
          <table className={styles.table}>
            <thead><tr><th>job</th><th>schedule</th><th>mode</th><th>delivers</th><th>last run</th><th>runs 24h</th><th>tokens 24h / 7d</th><th>directive</th></tr></thead>
            <tbody>{rows.map((j) => <FleetJobRow key={j.job_id} job={j} presets={jobs.data?.presets ?? {}} />)}</tbody>
          </table>
        </div>
        <p className={styles.foot}>{jobs.data?.note}</p>
      </section>

      <section className="panel">
        <div className="panel-heading"><div><h3>Directives</h3><p>newest first · applied by the gateway at once, or pending for the host bridge · previous value kept</p></div></div>
        <div style={{ padding: '10px 17px 14px', display: 'grid', gap: 4, fontSize: 11 }}>
          {(directives.data?.directives ?? []).length === 0 && <span className="tone-dim">No directives yet.</span>}
          {(directives.data?.directives ?? []).map((d) => (
            <div key={d.id} style={{ display: 'grid', gridTemplateColumns: 'auto minmax(0,1fr) auto auto', gap: 12 }}>
              <span className={d.status === 'applied' ? 'tone-good' : d.status === 'failed' ? 'tone-bad' : 'tone-warn'}>{d.status}{d.channel ? ` · ${d.channel === 'api' ? 'gateway' : 'bridge'}` : ''}</span>
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={d.detail}>{d.name ?? d.job_id} · {d.kind.split('_').join(' ')} {Object.keys(d.payload).length ? JSON.stringify(d.payload) : ''}{d.previous ? ` (was ${JSON.stringify(d.previous)})` : ''}{d.detail ? ` · ${d.detail}` : ''}</span>
              <span className={styles.mono}>{d.requested_by}</span>
              <span className={styles.mono}>{new Date(d.requested_at).toUTCString().slice(5, 22)}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}
