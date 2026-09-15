/** Feed heartbeats beside the integration pipeline's stages: transport evidence each service counts in memory since it started. */

export type FeedKind = 'websocket' | 'fetch' | 'route' | 'loop'

export interface FeedHeartbeat {
  id: string
  label: string
  kind: FeedKind
  service: string
  state: string
  connected: boolean
  state_since: string | null
  connected_since: string | null
  last_message_at: string | null
  last_success_at: string | null
  counts_1h: Record<string, number>
  attempts: number
  reconnects: number
  last_error: string | null
  last_error_at: string | null
  authority: string
  /** False where the feed's data carries no scoring weight anywhere in opportunity scoring. */
  scoring_influence: boolean
  influence: string
  detail: Record<string, unknown>
}

export interface FeedSource {
  ok: boolean
  counting_since: string | null
  reason: string | null
}

export interface PipelineFeeds {
  schema_version: 'pipeline_feeds_v1'
  generated_at: string
  sources: Record<string, FeedSource>
  feeds: FeedHeartbeat[]
  note: string
}
