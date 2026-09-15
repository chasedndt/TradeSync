import type { FeedHeartbeat } from '../../api/pipelineFeedTypes'

export type FeedTone = 'good' | 'warn' | 'bad'

const GOOD = new Set(['connected', 'ok'])
const WAITING = new Set(['not_started', 'connecting', 'waiting'])

/** Good while connected or answering, amber while starting or waiting, red for anything that stopped. */
export function feedTone(feed: Pick<FeedHeartbeat, 'state'>): FeedTone {
  if (GOOD.has(feed.state)) return 'good'
  if (WAITING.has(feed.state)) return 'warn'
  return 'bad'
}

export function stateLabel(feed: Pick<FeedHeartbeat, 'state' | 'kind'>): string {
  if (feed.state === 'ok') return feed.kind === 'loop' ? 'running' : 'answering'
  return feed.state.replace(/_/g, ' ')
}

/** What "delivered" means for this feed: a message for a stream, a pass for a loop, a successful fetch otherwise. */
export function deliveryLabel(feed: Pick<FeedHeartbeat, 'kind'>): string {
  return feed.kind === 'websocket' ? 'last message' : feed.kind === 'loop' ? 'last pass' : 'last successful fetch'
}

export function lastDelivery(feed: Pick<FeedHeartbeat, 'kind' | 'last_message_at' | 'last_success_at'>): string | null {
  return feed.kind === 'websocket' ? feed.last_message_at : feed.last_success_at
}

/** "42s ago", "5m ago", "3h ago", "2d ago", counted to the moment the heartbeats were read. */
export function ago(iso: string | null | undefined, nowMs: number): string {
  if (!iso) return '—'
  const s = Math.max(0, Math.round((nowMs - new Date(iso).getTime()) / 1000))
  if (s < 60) return `${s}s ago`
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return `${Math.floor(s / 86400)}d ago`
}

/** "15 Sep, 01:02:03": an absolute local time with seconds. */
export function stamp(iso: string | null | undefined): string {
  return iso ? new Date(iso).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '—'
}

const NOUNS: Record<string, [string, string]> = {
  messages: ['message', 'messages'],
  events: ['event stored', 'events stored'],
  fetches: ['fetch', 'fetches'],
  rows: ['row', 'rows'],
  requests: ['request', 'requests'],
  passes: ['pass', 'passes'],
  map_passes: ['map pass', 'map passes'],
  measurements: ['measurement', 'measurements'],
}

/** "3,412 messages · 1 event stored". */
export function countsLine(counts: Record<string, number>): string {
  const parts = Object.entries(counts).map(([key, n]) => {
    const [one, many] = NOUNS[key] ?? [key.replace(/_/g, ' '), key.replace(/_/g, ' ')]
    return `${n.toLocaleString('en-US')} ${n === 1 ? one : many}`
  })
  return parts.join(' · ') || 'nothing counted'
}
