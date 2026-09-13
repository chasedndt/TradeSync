import { useFleetJobs } from '../../api/hooks/useFleet'
import { useHermesStatus } from '../../api/hooks/useHermes'
import { FleetJobRow } from '../../pages/FleetJobRow'
import fleetStyles from '../../pages/Fleet.module.css'
import { formatAge } from '../home/format'
import styles from './Hermes.module.css'

// Jobs that serve trading: StrikeZone, Hyperliquid quant lab, thesis, proposals, evidence.
const TRADING = /strikezone|hyperliquid|thesis|trade|market|signal|quant|evidence|paper|proposal|scorecard|regime/i

/**
 * Hermes, the ChaseOS agent gateway, as TradeSync sees it: a heartbeat every
 * fifteen seconds (port, version, last answer, latency, recent availability),
 * the gateway's own platform states, and the trading jobs it runs, which can
 * be enabled, disabled and rescheduled here.
 */
export function HermesPanel() {
  const { data: h, isError } = useHermesStatus()
  const jobs = useFleetJobs()
  const trading = (jobs.data?.jobs ?? []).filter((j) => TRADING.test(`${j.name} ${j.script ?? ''}`))
  const status = h?.status ?? 'checking'
  const tone = status === 'live' ? 'tone-good' : status === 'offline' ? 'tone-bad' : 'tone-warn'
  const platforms = h?.gateway?.payload.platforms ?? {}
  const gatewayAge = h?.gateway?.snapshot_at ? (Date.now() - new Date(h.gateway.snapshot_at).getTime()) / 1000 : null

  return (
    <section className="panel" aria-labelledby="hermes-title">
      <div className={styles.head}>
        <span className={`${styles.dot} ${styles[status] ?? ''}`} aria-hidden="true" />
        <div>
          <h2 id="hermes-title">Hermes gateway</h2>
          <p>{h?.host ?? '—'}:{h?.port ?? '—'} · {h?.platform ?? 'hermes-agent'} {h?.version ?? ''} · {h?.api ?? ''} API</p>
        </div>
        <span className={`${styles.state} ${tone}`}>{status.toUpperCase()}</span>
      </div>
      {isError && <p className={styles.error}>Hermes status unavailable from the State API.</p>}

      <div className={styles.stats}>
        <div className={styles.stat}><span>last answer</span><strong>{h?.seconds_since_seen != null ? formatAge(h.seconds_since_seen) : '—'}</strong></div>
        <div className={styles.stat}><span>latency</span><strong>{h?.latency_ms != null ? `${h.latency_ms} ms` : '—'}</strong></div>
        <div className={styles.stat}><span>recent availability</span><strong>{h?.availability_recent != null ? `${Math.round(h.availability_recent * 100)}%` : '—'}</strong></div>
        <div className={styles.stat}><span>heartbeat</span><strong>every {h?.heartbeat_s ?? '—'}s</strong></div>
        <div className={styles.stat}><span>models</span><strong className={h?.models_ok === false ? 'tone-bad' : undefined}>{h?.models_ok === false ? 'key rejected' : (h?.models.join(', ') || '—')}</strong></div>
        <div className={styles.stat}><span>failures in a row</span><strong className={(h?.consecutive_failures ?? 0) > 0 ? 'tone-bad' : undefined}>{h?.consecutive_failures ?? 0}</strong></div>
      </div>

      <div className={styles.beats} aria-label="Recent heartbeats">
        <span className={styles.beatsLabel}>heartbeats</span>
        {(h?.checks ?? []).map((c) => (
          <span key={c.at} className={`${styles.beat} ${c.ok ? '' : styles.beatFail}`} title={`${c.at} · ${c.ok ? `${c.latency_ms} ms` : c.error}`} />
        ))}
        {h?.last_error && <span className="metric-sub tone-bad" style={{ marginLeft: 8 }}>{h.last_error}</span>}
      </div>

      <div className={styles.platforms}>
        {Object.keys(platforms).length === 0 && <span className="metric-sub">Gateway platform states arrive with the fleet bridge every five minutes.</span>}
        {Object.entries(platforms).map(([name, p]) => (
          <span key={name} className={styles.platform} title={p.error_message ?? undefined}>
            {name.replace('_', ' ')} <b className={p.state === 'connected' || p.state === 'running' ? 'tone-good' : p.state === 'retrying' ? 'tone-warn' : 'tone-bad'}>{p.state}</b>
          </span>
        ))}
        {h?.gateway?.payload.gateway_state && (
          <span className={styles.platform}>gateway <b>{h.gateway.payload.gateway_state}</b> · pid {h.gateway.payload.pid ?? '—'} · read {formatAge(gatewayAge)}</span>
        )}
      </div>

      <div className={styles.jobsHead}>
        <h3>Trading jobs</h3>
        <span className="metric-sub">{trading.length} of {jobs.data?.jobs.length ?? 0} Hermes jobs · change a schedule or switch a job off; the bridge applies it with a backup</span>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table className={fleetStyles.table}>
          <thead><tr><th>job</th><th>schedule</th><th>mode</th><th>delivers</th><th>last run</th><th>runs 24h</th><th>tokens 24h / 7d</th><th>directive</th></tr></thead>
          <tbody>{trading.map((j) => <FleetJobRow key={j.job_id} job={j} presets={jobs.data?.presets ?? {}} />)}</tbody>
        </table>
      </div>
    </section>
  )
}
