import { useQueryClient } from '@tanstack/react-query'
import { EventsStrip } from '../components/EventsStrip'
import { MarketPulse } from '../components/home/MarketPulse'
import { MarketThesisCard } from '../components/home/MarketThesisCard'
import { OpportunitiesPanel } from '../components/home/OpportunitiesPanel'
import { ReadinessBar } from '../components/home/ReadinessBar'
import { formatAge } from '../components/home/format'
import homeStyles from '../components/home/Home.module.css'
import { ChartLineUp, Flask, Heartbeat, Prohibit, Robot } from '../components/icons'
import { minutesAgo } from '../components/ledger/format'
import { useContextOverview, useHealth, useMarketSnapshots, useOpportunities, useSnapshot } from '../api/hooks'
import { useHermesStatus } from '../api/hooks/useHermes'
import { useLabHealth } from '../api/hooks/useStrikeZone'
import type { MarketSnapshotWithMicrostructure, Opportunity } from '../api/types'
import { ContextPanel, HealthItem } from './OverviewParts'

/**
 * Mission Control. Top to bottom in the order a trader reads it: readiness in
 * one line, the Market Thesis, the markets (each opens its own chart) beside
 * this week's events, open paper opportunities, then context and health.
 */
export function Overview() {
  const { data: marketData, isError: marketError } = useMarketSnapshots()
  const { data: context } = useContextOverview()
  const { data: health, isError: healthError } = useHealth()
  const { data: snapshot } = useSnapshot()
  const { data: opportunities, isLoading: opportunitiesLoading } = useOpportunities('new', 50)
  const { data: hermes } = useHermesStatus()
  const { data: lab } = useLabHealth()
  const qc = useQueryClient()
  const snapshots = (marketData?.snapshots || []) as MarketSnapshotWithMicrostructure[]

  const observedAge = (item: MarketSnapshotWithMicrostructure) => item.snapshot_age_ms ?? item.data_age_ms
  const freshest = snapshots.length ? Math.min(...snapshots.map(observedAge)) / 1000 : null
  const oldest = snapshots.length ? Math.max(...snapshots.map(observedAge)) / 1000 : null
  const marketLive = !marketError && snapshots.length > 0 && (oldest ?? Infinity) < 20
  const marketState = marketError ? 'UNREACHABLE' : snapshots.length === 0 ? 'WAITING' : marketLive ? 'LIVE' : 'STALE'
  const redisHealthy = snapshot ? Object.values(snapshot.stream_lengths || {}).every((value) => value >= 0) : false
  const opps = (opportunities ?? []) as Opportunity[]
  const hasSignals = Boolean(snapshot?.latest_signal_ts)
  const hermesTone = hermes?.status === 'live' ? 'good' : hermes?.status === 'degraded' || hermes?.status === 'checking' ? 'warn' : 'bad'

  const queries = qc.getQueryCache().getAll()
  const failing = queries.filter((q) => q.state.status === 'error').length

  return (
    <div className="mission-control">
      <ReadinessBar
        chips={[
          { label: 'Market data', value: marketState, detail: oldest == null ? 'waiting' : `oldest ${formatAge(oldest)}`, tone: marketLive ? 'good' : marketError ? 'bad' : 'warn', to: '/pipeline', icon: <ChartLineUp size={16} weight="duotone" /> },
          { label: 'Pipeline', value: hasSignals ? 'ACTIVE' : 'PARTIAL', detail: `${opps.length} open opportunities`, tone: hasSignals ? 'good' : 'warn', to: '/pipeline', icon: <Heartbeat size={16} weight="duotone" /> },
          { label: 'Hermes', value: (hermes?.status ?? 'checking').toUpperCase(), detail: hermes?.seconds_since_seen != null ? `seen ${formatAge(hermes.seconds_since_seen)} · :${hermes.port}` : 'waiting for heartbeat', tone: hermesTone, to: '/agents', icon: <Robot size={16} weight="duotone" /> },
          { label: 'Forward test', value: lab?.ok === true ? 'OK' : lab?.ok === false ? 'HOLD' : 'WAITING', detail: lab ? `last call ${minutesAgo(lab.last_signal_age_minutes)}${lab.failing_jobs ? ` · ${lab.failing_jobs} jobs failing` : ''}` : 'no report yet', tone: lab?.ok === true ? 'good' : lab?.ok === false ? 'warn' : 'dim', to: '/signal-ledger', icon: <Flask size={16} weight="duotone" /> },
          { label: 'Execution', value: 'DISABLED', detail: 'paper only', tone: 'bad', to: '/execution', icon: <Prohibit size={16} weight="bold" /> },
        ]}
      />

      <MarketThesisCard />

      <div className={homeStyles.grid}>
        <MarketPulse snapshots={snapshots} />
        <EventsStrip context={context} />
      </div>

      <OpportunitiesPanel opps={opps} loading={opportunitiesLoading} />

      <div className="bottom-grid">
        <section className="panel" aria-labelledby="system-health-title">
          <div className="panel-heading"><div><h2 id="system-health-title">System Health</h2><p>runtime evidence, including what this page failed to fetch</p></div></div>
          <div className="health-grid health-grid--compact">
            <HealthItem name="PostgreSQL" state={health?.postgres ? 'HEALTHY' : 'UNAVAILABLE'} detail={health?.latency_ms != null ? `${health.latency_ms.toFixed(0)}ms` : '—'} tone={health?.postgres ? 'good' : 'bad'} />
            <HealthItem name="Redis" state={redisHealthy ? 'HEALTHY' : 'UNAVAILABLE'} detail={redisHealthy ? 'stream checks pass' : '—'} tone={redisHealthy ? 'good' : 'bad'} />
            <HealthItem name="Hyperliquid data" state={marketState} detail={freshest == null ? '—' : `newest ${formatAge(freshest)} · oldest ${formatAge(oldest)}`} tone={marketLive ? 'good' : marketError ? 'bad' : 'warn'} />
            <HealthItem name="State API" state={!healthError && health ? 'HEALTHY' : 'UNAVAILABLE'} detail={health ? `${health.latency_ms.toFixed(0)}ms DB read` : '—'} tone={!healthError && health ? 'good' : 'bad'} />
            <HealthItem name="Cockpit fetches" state={failing === 0 ? 'ALL OK' : `${failing} FAILING`} detail={`${queries.length - failing}/${queries.length} answering`} tone={failing === 0 ? 'good' : 'bad'} />
            <HealthItem name="Hermes gateway" state={(hermes?.status ?? 'checking').toUpperCase()} detail={hermes?.latency_ms != null ? `${hermes.latency_ms}ms · ${Math.round((hermes.availability_recent ?? 0) * 100)}% up` : '—'} tone={hermesTone} />
          </div>
        </section>
        <ContextPanel context={context} />
      </div>
    </div>
  )
}
