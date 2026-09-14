import { useQuery } from '@tanstack/react-query'
import { apiGet } from '../client'
import type {
  ActiveRulebookResponse,
  Attribution,
  OpportunityAttributionResponse,
  ProposalsResponse,
  ScoreboardResponse,
  VerdictsResponse,
} from '../learningTypes'

/** Read side of opportunity learning. Every key starts with 'learning' so an action can refresh them together. */

export function useLearningScoreboard(days: number) {
  return useQuery({
    queryKey: ['learning', 'scoreboard', days],
    queryFn: () => apiGet<ScoreboardResponse>(`/state/learning/scoreboard?days=${days}`),
    refetchInterval: 60_000,
    retry: 1,
  })
}

export function useLearningFailures(horizon: number, limit = 12) {
  return useQuery({
    queryKey: ['learning', 'failures', horizon, limit],
    queryFn: () => apiGet<{ failures: Attribution[] }>(`/state/learning/failures?horizon=${horizon}&limit=${limit}`),
    refetchInterval: 60_000,
    retry: 1,
  })
}

export function useLearningVerdicts(horizon: number, days: number) {
  return useQuery({
    queryKey: ['learning', 'verdicts', horizon, days],
    queryFn: () => apiGet<VerdictsResponse>(`/state/learning/verdicts?horizon=${horizon}&days=${days}`),
    refetchInterval: 120_000,
    retry: 1,
  })
}

export function useLearningProposals() {
  return useQuery({
    queryKey: ['learning', 'proposals'],
    queryFn: () => apiGet<ProposalsResponse>('/state/learning/proposals?limit=10'),
    refetchInterval: 30_000,
    retry: 1,
  })
}

export function useActiveRulebook() {
  return useQuery({
    queryKey: ['learning', 'active'],
    queryFn: () => apiGet<ActiveRulebookResponse>('/state/learning/active'),
    refetchInterval: 30_000,
    retry: 1,
  })
}

export function useOpportunityAttribution(opportunityId: string | undefined) {
  return useQuery({
    queryKey: ['learning', 'opportunity', opportunityId],
    queryFn: () => apiGet<OpportunityAttributionResponse>(`/state/opportunities/${opportunityId}/attribution`),
    enabled: !!opportunityId,
    refetchInterval: 60_000,
    retry: 1,
  })
}
