import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPost } from '../client'
import type {
  RegimeLabExperimentList,
  RegimeLabExperimentRequest,
  RegimeLabOverview,
  RegimeLabSaveResponse,
  ReplayJudgement,
  ReplayRequest,
} from '../regimeLabTypes'

/** TradeSync reads and trades Hyperliquid only. */
const VENUE = 'hyperliquid'

export function useRegimeLabOverview(symbol: string) {
  return useQuery({
    queryKey: ['regime-lab', 'overview', symbol],
    queryFn: () => apiGet<RegimeLabOverview>(
      `/state/regime-lab/overview?venue=${VENUE}&symbol=${encodeURIComponent(symbol)}`,
    ),
    refetchInterval: 15_000,
    retry: 1,
  })
}

/** Judge challenger weights by replaying stored decisions. */
export function useReplayChallenger() {
  return useMutation({
    mutationFn: (body: ReplayRequest) => apiPost<ReplayJudgement>('/state/regime-lab/replay', body),
  })
}

/** Save a draft; the server replays it again and stores that judgement. */
export function useSaveExperiment() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: RegimeLabExperimentRequest) =>
      apiPost<RegimeLabSaveResponse>('/state/regime-lab/experiments', body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['regime-lab', 'experiments'] }),
  })
}

export function useRegimeLabExperiments(limit = 8) {
  return useQuery({
    queryKey: ['regime-lab', 'experiments', limit],
    queryFn: () => apiGet<RegimeLabExperimentList>(`/state/regime-lab/experiments?limit=${limit}`),
    retry: false,
  })
}
