import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPost } from '../client'
import type {
  RegimeLabEvaluationResponse,
  RegimeLabExperimentList,
  RegimeLabExperimentRequest,
  RegimeLabOverview,
} from '../types'

function query(venue: string, symbol: string) {
  return `venue=${encodeURIComponent(venue)}&symbol=${encodeURIComponent(symbol)}`
}

export function useRegimeLabOverview(venue: string, symbol: string) {
  return useQuery({
    queryKey: ['regime-lab', 'overview', venue, symbol],
    queryFn: () => apiGet<RegimeLabOverview>(
      `/state/regime-lab/overview?${query(venue, symbol)}`
    ),
    refetchInterval: 15000,
    retry: 1,
  })
}

export function useEvaluateRegimeLab(venue: string, symbol: string) {
  return useMutation({
    mutationFn: (body: RegimeLabExperimentRequest) =>
      apiPost<RegimeLabEvaluationResponse>(
        `/state/regime-lab/evaluate?${query(venue, symbol)}`,
        body,
      ),
  })
}

export function useSaveRegimeLab(venue: string, symbol: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: RegimeLabExperimentRequest) =>
      apiPost<{ saved: boolean; experiment_id: string; status: string }>(
        `/state/regime-lab/experiments?${query(venue, symbol)}`,
        body,
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['regime-lab', 'experiments'] }),
  })
}

export function useRegimeLabExperiments() {
  return useQuery({
    queryKey: ['regime-lab', 'experiments'],
    queryFn: () => apiGet<RegimeLabExperimentList>('/state/regime-lab/experiments?limit=8'),
    retry: false,
  })
}
