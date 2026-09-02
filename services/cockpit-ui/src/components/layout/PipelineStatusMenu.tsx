import { NavLink } from 'react-router-dom'
import { FlowArrow } from '../icons'
import { useIntegrationPipeline } from '../../api/hooks'
import type { PipelineNodeStatus } from '../../api/types'

function tone(status?: PipelineNodeStatus | 'ready') {
  if (status === 'live' || status === 'healthy' || status === 'ready') return 'good'
  if (status === 'partial' || status === 'contract_only' || status === 'planned') return 'warn'
  if (status === 'offline') return 'bad'
  return 'dim'
}

function label(status?: string) {
  return (status || 'checking').replace(/_/g, ' ')
}

export function PipelineStatusMenu() {
  const { data, isError } = useIntegrationPipeline()
  const pipelineStatus = isError ? 'offline' : data?.tier_a.status
  const chase = data?.nodes.find((node) => node.id === 'chaseos')
  const rows = data?.nodes.filter((node) => (
    ['market_data', 'scorer_fusion', 'tradingview_pine', 'strike_zone', 'agent_harness', 'chaseos'].includes(node.id)
  )) || []

  return (
    <div className="pipeline-status-menu">
      <NavLink
        to="/pipeline"
        className="pipeline-status-trigger"
        aria-label={`Open integration pipeline. Tier A ${label(pipelineStatus)}. ChaseOS ${label(chase?.status)}.`}
      >
        <FlowArrow size={18} weight="duotone" />
        <span><small>Tier A</small><strong className={`tone-${tone(pipelineStatus)}`}>{label(pipelineStatus)}</strong></span>
        {data && <em>{data.tier_a.ready_count}/{data.tier_a.total_count}</em>}
        <span className="pipeline-trigger-divider" />
        <span className="pipeline-trigger-chase"><i className={`status-dot status-dot--${tone(chase?.status)}`} />ChaseOS <b>{label(chase?.status)}</b></span>
      </NavLink>
      <div className="pipeline-status-popover" role="tooltip">
        <div className="pipeline-popover-heading">
          <span>Integration pipeline</span>
          <strong className={`tone-${tone(pipelineStatus)}`}>{label(pipelineStatus)}</strong>
        </div>
        {rows.map((node) => (
          <div className="pipeline-popover-row" key={node.id}>
            <span><i className={`status-dot status-dot--${tone(node.status)}`} />{node.label}</span>
            <strong>{label(node.status)}</strong>
          </div>
        ))}
        <p>{data?.tier_a.principle || 'Checking live dependencies and declared connector contracts.'}</p>
        <span className="pipeline-popover-action">Open inspector for missing links and restart targets →</span>
      </div>
    </div>
  )
}
