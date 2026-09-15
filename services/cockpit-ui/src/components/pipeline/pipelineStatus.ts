import type { PipelineNodeStatus } from '../../api/types'

export const statusLabels: Record<PipelineNodeStatus, string> = {
  live: 'Live',
  healthy: 'Healthy',
  partial: 'Partial',
  offline: 'Offline',
  contract_only: 'Connection unverified',
  planned: 'Planned',
  locked: 'Locked',
}

export function tone(status: PipelineNodeStatus) {
  if (status === 'live' || status === 'healthy') return 'good'
  if (status === 'partial' || status === 'contract_only' || status === 'planned') return 'warn'
  if (status === 'locked') return 'dim'
  return 'bad'
}

export function readable(value: string) {
  return value.replace(/_/g, ' ')
}
