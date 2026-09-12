import { useQueries, useQuery } from '@tanstack/react-query'
import { apiGet } from '../client'
import type { AgentPostPayload, HarnessStatus, QuarantineItem, QuarantineList, SourceCardsResponse } from '../types'

/**
 * What each external source has earned: claims extracted from held material,
 * measured like paper opportunities, Holm-adjusted together with the skill
 * gate's costs. A slow read; refreshes on a long interval.
 */
export function useSourceCards(symbol?: string) {
  return useQuery({
    queryKey: ['source-cards', symbol ?? 'all'],
    queryFn: () => apiGet<SourceCardsResponse>(`/state/outcomes/source-cards${symbol ? `?symbol=${encodeURIComponent(symbol)}` : ''}`),
    refetchInterval: 300_000,
    staleTime: 120_000,
    retry: 1,
  })
}

export type AgentPost = QuarantineItem & { payload: AgentPostPayload }

const isAgentPost = (item: QuarantineItem): item is AgentPost => {
  const v = (item.payload as { schema_version?: string }).schema_version
  return v === 'discord_message_v1' || v === 'hermes_job_output_v1'
}

/**
 * What the ChaseOS fleet produced, from both bridges: Discord posts read by
 * the discord-reader (source `discord`) and job outputs read from the Hermes
 * runtime by the host bridge (source `chaseos`). Untrusted material with
 * provenance; nothing here scores.
 */
export function useAgentFeed(limit = 200) {
  const results = useQueries({
    queries: ['discord', 'chaseos'].map((source) => ({
      queryKey: ['agent-feed', source, limit],
      queryFn: () => apiGet<QuarantineList>(`/state/quarantine?source=${source}&limit=${limit}`),
      refetchInterval: 30_000,
      staleTime: 15_000,
      retry: 1,
    })),
  })
  const items = results
    .flatMap((r) => r.data?.items ?? [])
    .filter(isAgentPost)
    .sort((a, b) => (a.received_at < b.received_at ? 1 : -1))
  return {
    items,
    note: results.find((r) => r.data)?.data?.note ?? '',
    isLoading: results.some((r) => r.isLoading),
    isError: results.every((r) => r.isError),
  }
}

/** Whether an advisory harness runtime is reachable, and its enforced boundary. */
export function useHarnessStatus() {
  return useQuery({
    queryKey: ['harness-status'],
    queryFn: () => apiGet<HarnessStatus>('/state/agents/harness/status'),
    refetchInterval: 60_000,
    retry: 1,
  })
}
