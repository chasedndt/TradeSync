import {
  BracketsCurly,
  ChartLineUp,
  Database,
  FlowArrow,
  GlobeHemisphereWest,
  HardDrives,
  Heartbeat,
  ListChecks,
  Prohibit,
  Robot,
  ShieldCheck,
  Stack,
  WarningCircle,
} from '../components/icons'
import { useIntegrationPipeline } from '../api/hooks'
import type { PipelineNode, PipelineNodeStatus } from '../api/types'

const statusLabels: Record<PipelineNodeStatus, string> = {
  live: 'Live',
  healthy: 'Healthy',
  partial: 'Partial',
  offline: 'Offline',
  contract_only: 'Contract only',
  planned: 'Planned',
  locked: 'Locked',
}

const nodeIcons: Record<string, typeof Heartbeat> = {
  hyperliquid: GlobeHemisphereWest,
  market_data: ChartLineUp,
  redis: Stack,
  postgres: HardDrives,
  regime_engine: BracketsCurly,
  scorer_fusion: FlowArrow,
  performance_journal: ListChecks,
  tradingview_pine: ChartLineUp,
  strike_zone: ShieldCheck,
  agent_harness: Robot,
  chaseos: Database,
  execution: Prohibit,
}

function tone(status: PipelineNodeStatus) {
  if (status === 'live' || status === 'healthy') return 'good'
  if (status === 'partial' || status === 'contract_only' || status === 'planned') return 'warn'
  if (status === 'locked') return 'dim'
  return 'bad'
}

function readable(value: string) {
  return value.replace(/_/g, ' ')
}

function PipelineNodeCard({ node }: { node: PipelineNode }) {
  const Icon = nodeIcons[node.id] || Heartbeat
  const stateTone = tone(node.status)

  return (
    <details className={`pipeline-node pipeline-node--${stateTone}`}>
      <summary>
        <span className={`pipeline-node-icon tone-${stateTone}`}><Icon size={23} weight="duotone" /></span>
        <span className="pipeline-node-heading">
          <span>{node.stage.replace(/_/g, ' ')} · Tier {node.tier}</span>
          <strong>{node.label}</strong>
          <small>{node.summary}</small>
        </span>
        <span className={`pipeline-state pipeline-state--${stateTone}`}>
          <span className="status-dot" />{statusLabels[node.status]}
          {/* A state without a duration is half a fact: "offline" reads the
              same whether it started ten seconds ago or yesterday. */}
          {node.state_age && node.state_age !== 'unknown' && (
            <small className="pipeline-state-age">for {node.state_age}</small>
          )}
          {node.flapping && (
            <small className="pipeline-state-flap" title={`${node.recent_transitions} changes in 15 minutes`}>
              unstable
            </small>
          )}
        </span>
      </summary>
      <div className="pipeline-node-detail">
        <div>
          <span className="pipeline-detail-label">Verified evidence</span>
          <ul>{node.evidence.map((item) => <li key={item}>{item}</li>)}</ul>
        </div>
        <div>
          <span className="pipeline-detail-label">Missing or gated</span>
          {node.missing.length
            ? <ul>{node.missing.map((item) => <li key={item}>{item}</li>)}</ul>
            : <p>Nothing currently reported missing.</p>}
        </div>
        <div className="pipeline-recovery-callout">
          <span className="pipeline-detail-label">Impact</span>
          <p>{node.impact}</p>
          <span className="pipeline-detail-label">Next action · {readable(node.recovery.kind)}</span>
          <strong>{node.recovery.label}</strong>
          <small>Target: {node.recovery.target}</small>
          {node.recovery.command && <code>{node.recovery.command}</code>}
        </div>
      </div>
    </details>
  )
}

export function Pipeline() {
  const { data, isLoading, isError, refetch, isFetching } = useIntegrationPipeline()

  if (isLoading) {
    return <section className="panel pipeline-loading"><Heartbeat size={28} weight="duotone" />Inspecting the runtime pipeline…</section>
  }

  if (isError || !data) {
    return (
      <section className="panel pipeline-error">
        <WarningCircle size={30} weight="duotone" />
        <div><h2>Pipeline status is unavailable</h2><p>The inspector API did not answer. TradeSync has not inferred component states.</p></div>
        <button type="button" onClick={() => refetch()}>Retry inspection</button>
      </section>
    )
  }

  const tierANodes = data.nodes.filter((node) => node.required_for_tier_a)
  const connectorNodes = data.nodes.filter((node) => !node.required_for_tier_a)
  const nodeLabels = Object.fromEntries(data.nodes.map((node) => [node.id, node.label]))
  const tierTone = data.tier_a.status === 'ready' ? 'good' : data.tier_a.status === 'partial' ? 'warn' : 'bad'
  const coreRecovery = data.recovery_queue.filter((item) => item.required_for_tier_a)

  return (
    <div className="pipeline-page">
      <section className="panel pipeline-hero">
        <div>
          <span className="pipeline-kicker">Runtime topology · live probes + declared contracts</span>
          <h2>Integration Pipeline</h2>
          <p>Inspect what is flowing, what is only partially implemented, what can be restarted, and what still needs an adapter. Optional systems enrich TradeSync; they never become Tier A startup dependencies.</p>
        </div>
        <button type="button" className="pipeline-refresh" onClick={() => refetch()} disabled={isFetching}>
          <Heartbeat size={18} weight="duotone" />{isFetching ? 'Inspecting…' : 'Refresh probes'}
        </button>
      </section>

      <section className="pipeline-summary-grid" aria-label="Pipeline summary">
        <article className="panel pipeline-summary-card">
          <span>Tier A core</span>
          <strong className={`tone-${tierTone}`}>{data.tier_a.status.toUpperCase()}</strong>
          <small>{data.tier_a.ready_count}/{data.tier_a.total_count} stages fully ready</small>
        </article>
        <article className="panel pipeline-summary-card">
          <span>Federated connectors</span>
          <strong>{data.federated.connected_count}/{data.federated.total_count}</strong>
          <small>live optional connections</small>
        </article>
        <article className="panel pipeline-summary-card">
          <span>Operating mode</span>
          <strong>PAPER</strong>
          <small>market observation and governed research</small>
        </article>
        <article className="panel pipeline-summary-card">
          <span>Execution authority</span>
          <strong className="tone-bad">LOCKED</strong>
          <small>no wallet or signer in this runtime</small>
        </article>
      </section>

      <section className="panel pipeline-section" aria-labelledby="tier-a-path-title">
        <div className="panel-heading pipeline-section-heading">
          <div><h2 id="tier-a-path-title">Tier A operating path</h2><p>Core capability—expand any stage to inspect evidence and recovery.</p></div>
          <span className={`pipeline-state pipeline-state--${tierTone}`}><span className="status-dot" />{data.tier_a.status}</span>
        </div>
        <div className="pipeline-node-list">
          {tierANodes.map((node) => <PipelineNodeCard key={node.id} node={node} />)}
        </div>
      </section>

      <section className="panel pipeline-section" aria-labelledby="connector-path-title">
        <div className="panel-heading pipeline-section-heading">
          <div><h2 id="connector-path-title">Federated intelligence</h2><p>ChaseOS, Strike Zone Crypto, Pine Script, and agent harnesses remain independently recoverable.</p></div>
          <span>{data.federated.connected_count} live</span>
        </div>
        <div className="pipeline-connector-grid">
          {connectorNodes.map((node) => <PipelineNodeCard key={node.id} node={node} />)}
        </div>
      </section>

      <div className="pipeline-lower-grid">
        <section className="panel pipeline-section" aria-labelledby="flow-map-title">
          <div className="panel-heading pipeline-section-heading">
            <div><h2 id="flow-map-title">Workflow edges</h2><p>Every edge declares whether data is flowing, partial, disconnected, or locked.</p></div>
          </div>
          <div className="pipeline-edge-list">
            {data.edges.map((edge) => (
              <div className="pipeline-edge" key={`${edge.from}-${edge.to}`}>
                <span>{nodeLabels[edge.from]}</span>
                <span className={`pipeline-edge-line pipeline-edge-line--${edge.status}`}><FlowArrow size={19} />{readable(edge.status)}</span>
                <span>{nodeLabels[edge.to]}</span>
                <small>{edge.label}</small>
              </div>
            ))}
          </div>
        </section>

        <section className="panel pipeline-section" aria-labelledby="gaps-title">
          <div className="panel-heading pipeline-section-heading">
            <div><h2 id="gaps-title">Explicit capability gaps</h2><p>Missing fields never become fabricated evidence.</p></div>
          </div>
          <div className="pipeline-gap-list">
            {data.capability_gaps.map((gap) => (
              <article key={gap.id}>
                <div><strong>{readable(gap.id)}</strong><span>{readable(gap.status)}</span></div>
                <p><b>Blocks:</b> {gap.blocking}</p>
                <p>{gap.next_action}</p>
              </article>
            ))}
          </div>
        </section>
      </div>

      <section className="panel pipeline-section" aria-labelledby="recovery-title">
        <div className="panel-heading pipeline-section-heading">
          <div><h2 id="recovery-title">Recovery queue</h2><p>Core blockers first; connector work follows without stopping standalone TradeSync.</p></div>
          <span>{coreRecovery.length} Tier A items</span>
        </div>
        <div className="table-scroll">
          <table className="pipeline-recovery-table">
            <thead><tr><th>Component</th><th>State</th><th>What is missing</th><th>What to do</th><th>Restart target</th></tr></thead>
            <tbody>
              {data.recovery_queue.map((item) => (
                <tr key={item.node_id}>
                  <td><strong>{item.label}</strong><small>{item.required_for_tier_a ? 'Tier A core' : 'Optional connector'}</small></td>
                  <td><span className={`pipeline-state pipeline-state--${tone(item.status)}`}>{statusLabels[item.status]}</span></td>
                  <td>{item.missing.join(' · ') || 'No missing contract fields'}</td>
                  <td>{item.recovery.label}</td>
                  <td><code>{item.recovery.target}</code></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="pipeline-contract-note"><ShieldCheck size={18} weight="duotone" />Generated {new Date(data.generated_at).toLocaleString()} · {data.schema_version} · execution authority false</div>
      </section>
    </div>
  )
}
