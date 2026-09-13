import { useQuery } from '@tanstack/react-query'
import { apiGet } from '../client'
import type { EventReactionsResponse, HermesLinkStatus } from '../types'

/** The Hermes gateway link as of the last heartbeat. Answers instantly; the heartbeat runs server-side. */
export function useHermesStatus() {
  return useQuery({
    queryKey: ['hermes-status'],
    queryFn: () => apiGet<HermesLinkStatus>('/state/hermes/status'),
    refetchInterval: 10_000,
    retry: 1,
  })
}

/** This week's key events with measured past reactions and recent coverage. */
export function useEventReactions() {
  return useQuery({
    queryKey: ['event-reactions'],
    queryFn: () => apiGet<EventReactionsResponse>('/state/market/event-reactions'),
    refetchInterval: 300_000,
    staleTime: 120_000,
    retry: 1,
  })
}
