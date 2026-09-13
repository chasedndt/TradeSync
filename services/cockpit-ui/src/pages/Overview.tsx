import { useState } from 'react'
import { NavLink } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { MarketChartPanel } from '../components/canvas/MarketChartPanel'
import { EventsStrip } from '../components/EventsStrip'
import { ChartLineUp, Heartbeat, Prohibit } from '../components/icons'
import { useContextOverview, useHealth, useMarketSnapshots, useOpportunities, useSnapshot } from '../api/hooks'
import { useEditions } from '../api/hooks/useEditions'
import type { MarketSnapshotWithMicrostructure, Opportunity } from '../api/types'
import { ContextPanel, HealthItem, MarketPulse, ReadinessItem, formatAge } from './OverviewParts'

/**
 * Mission Control, fitted to one screen: a thin readiness bar, the events
 * strip, the market table driving the chart beside it, live paper
 * opportunities, the latest thesis edition, context, and a health row that
 * reports what the Cockpit itself failed to fetch.
 */
export function Overview() {
  const { data: marketData, isError: marketError } = useMarketSnapshots()
  const { data: context } = useContextOverview()
  const { data: health, isError: healthError } = useHealth()
  const { data: snapshot } = useSnapshot()
  const { data: opportunities, isLoading: opportunitiesLoading } = useOpportunities('new', 50)
  const { data: editions } = useEditions(1)
  const qc = useQueryClient()
  const snapshots = (marketData?.snapshots || []) as MarketSnapshotWithMicrostructure[]
  const [selected, setSelected] = useState<string | null>(null)

  const observedAge = (item: MarketSnapshotWithMicrostructure) => item.snapshot_age_ms ?? item.data_age_ms
  const freshest = snapshots.length ? Math.min(...snapshots.map(observedAge)) / 1000 : null
  const oldest = snapshots.length ? Math.max(...snapshots.map(observedAge)) / 1000 : null
  const marketLive = !marketError && snapshots.length > 0 && (oldest ?? Infinity) < 20
  const marketState = marketError ? 'UNREACHABLE' : snapshots.length === 0 ? 'WAITING' : marketLive ? 'LIVE' : 'STALE'
  const redisHealthy = snapshot ? Object.values(snapshot.stream_lengths || {}).every((value) => value >= 0) : false
  const opps = (opportunities ?? []) as Opportunity[]
  const hasSignals = Boolean(snapshot?.latest_signal_ts)
  const chartSymbol = selected ?? snapshots[0]?.symbol
  const latestEdition = editions?.editions[0]

  // What the Cockpit itself could not fetch in the last cycle. A page with
  // failing requests must not report "healthy" because one probe answered.
  const failing = qc.getQueryCache().getAll().filter((q) => q.state.status === 'error').length
  const totalQueries = qc.getQueryCache().getAll().length

  return (
    <div className="mission-control">
      <section className="panel readiness-strip readiness-strip--compact" aria-label="System readiness">
        <ReadinessItem to="/pipeline" icon={<ChartLineUp size={22} weight="duotone" />} label="Market data" value={marketState} detail={oldest == null ? 'waiting for data' : `oldest symbol ${formatAge(oldest)}`} tone={marketLive ? 'good' : marketError ? 'bad' : 'warn'} />
        <ReadinessItem to="/pipeline" icon={<Heartbeat size={22} weight="duotone" />} label="Intelligence pipeline" value={hasSignals ? 'ACTIVE' : 'PARTIAL'} detail={hasSignals ? `${opps.length} open paper opportunities` : 'no current scoring output'} tone={hasSignals ? 'good' : 'warn'} />
        <ReadinessItem to="/execution" icon={<Prohibit size={22} weight="bold" />} label="Execution" value="DISABLED" detail="paper only · no wallet" tone="bad" />
      </section>

      <EventsStrip context={context} />

      <div className="primary-grid">
        <MarketPulse snapshots={snapshots} selected={chartSymbol} onSelect={setSelected} />
        <div style={{ display: 'grid', gap: 16, alignContent: 'start' }}>
          <MarketChartPanel symbol={chartSymbol} onSymbolChange={setSelected} height={220} />
          <OpportunitiesPanel opps={opps} loading={opportunitiesLoading} />
        </div>
      </div>

      <div className="bottom-grid">
        <section className="panel" aria-labelledby="edition-home-title">
          <div className="panel-heading">
            <div><h2 id="edition-home-title">Latest thesis edition</h2><p>{latestEdition ? `${latestEdition.edition} · ${new Date(latestEdition.generated_at).toUTCString().slice(5, 22)}` : 'no edition yet'}</p></div>
            <NavLink to="/thesis" className="panel-action">Open thesis →</NavLink>
          </div>
          <div className="edition-card">
            {latestEdition ? (
              <>
                <strong>{latestEdition.headline}</strong>
                <div>
                  {latestEdition.symbols.map((s) => (
                    <span key={s} className={`pill ${latestEdition.verdicts[s] === 'NO TRADE' ? 'pill--bad' : 'pill--warn'}`}>{s.replace('-PERP', '')}</span>
                  ))}
                </div>
                <span className="metric-sub">{latestEdition.media.video ? 'narration and video attached' : 'narration pending'} · private, not for publication</span>
              </>
            ) : (
              <span className="tone-dim">The first scheduled edition is {editions?.schedule.next.edition ?? '—'} at {editions?.schedule.next.at ? new Date(editions.schedule.next.at).toUTCString().slice(17, 22) : '—'} UTC.</span>
            )}
          </div>
        </section>
        <ContextPanel context={context} />
      </div>

      <section className="panel" aria-labelledby="system-health-title">
        <div className="panel-heading"><div><h2 id="system-health-title">System health</h2><p>runtime evidence, including what this page failed to fetch</p></div></div>
        <div className="health-grid health-grid--compact">
          <HealthItem name="PostgreSQL" state={health?.postgres ? 'HEALTHY' : 'UNAVAILABLE'} detail={health?.latency_ms != null ? `${health.latency_ms.toFixed(0)}ms` : '—'} tone={health?.postgres ? 'good' : 'bad'} />
          <HealthItem name="Redis" state={redisHealthy ? 'HEALTHY' : 'UNAVAILABLE'} detail={redisHealthy ? 'stream checks pass' : '—'} tone={redisHealthy ? 'good' : 'bad'} />
          <HealthItem name="Hyperliquid data" state={marketState} detail={freshest == null ? '—' : `newest ${formatAge(freshest)} · oldest ${formatAge(oldest)}`} tone={marketLive ? 'good' : marketError ? 'bad' : 'warn'} />
          <HealthItem name="State API" state={!healthError && health ? 'HEALTHY' : 'UNAVAILABLE'} detail={health ? `${health.latency_ms.toFixed(0)}ms DB read` : '—'} tone={!healthError && health ? 'good' : 'bad'} />
          <HealthItem name="Cockpit fetches" state={failing === 0 ? 'ALL OK' : `${failing} FAILING`} detail={`${totalQueries - failing}/${totalQueries} queries answering`} tone={failing === 0 ? 'good' : 'bad'} />
          <HealthItem name="Scorer / fusion" state={hasSignals ? (opps.length ? 'OUTPUT SEEN' : 'SIGNALS ONLY') : 'NO OUTPUT'} detail={hasSignals ? `${opps.length} open opportunities` : 'not measured directly'} tone={hasSignals ? 'good' : 'warn'} />
        </div>
      </section>
    </div>
  )
}

function OpportunitiesPanel({ opps, loading }: { opps: Opportunity[]; loading: boolean }) {
  const shown = opps.slice(0, 6)
  return (
    <section className="panel" aria-labelledby="paper-opps-title">
      <div className="panel-heading">
        <div><h2 id="paper-opps-title">Paper opportunities</h2><p>{loading ? 'checking…' : `${opps.length} open · newest first`}</p></div>
        <NavLink to="/opportunities" className="panel-action">All →</NavLink>
      </div>
      {shown.length === 0 ? (
        <p className="tone-dim" style={{ padding: '10px 17px 14px', margin: 0, fontSize: 12 }}>{loading ? 'Checking scoring output…' : 'No open paper opportunity right now. The scorer records a verdict every cycle; an opportunity appears when a side is admitted.'}</p>
      ) : (
        <ul className="opps-list">
          {shown.map((o) => (
            <NavLink key={o.id} to={`/opportunities/${o.id}`} className="opps-row">
              <span className={`pill ${o.dir === 'LONG' ? 'pill--good' : 'pill--bad'}`}>{o.dir}</span>
              <span><strong>{o.symbol.replace('-PERP', '')}</strong> <span className="metric-sub" style={{ display: 'inline' }}>bias {o.bias.toFixed(2)} · quality {Math.round(o.quality)}</span></span>
              <span className="metric-sub">{o.status}</span>
              <span className="metric-sub">{formatAge((Date.now() - new Date(o.snapshot_ts).getTime()) / 1000)}</span>
            </NavLink>
          ))}
        </ul>
      )}
    </section>
  )
}
