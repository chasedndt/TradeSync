import { useMutation, useQueryClient } from '@tanstack/react-query'
import { apiPost } from '../client'
import type { GenerateResponse } from '../learningTypes'

/**
 * Operator actions for opportunity learning. Adopt and revert change which
 * weights the paper scorer uses from its next cycle; both carry an explicit
 * confirmation and the operator's name. None of them touches execution.
 */

export interface Decision { decided_by: string; note: string }

function useRefreshLearning() {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: ['learning'] })
}

export function useAdoptProposal() {
  const refresh = useRefreshLearning()
  return useMutation({
    mutationFn: ({ id, decision }: { id: string; decision: Decision }) =>
      apiPost<{ adopted: boolean; version: string; note: string }>(`/state/learning/proposals/${id}/adopt`, { ...decision, confirm: true }),
    onSuccess: refresh,
  })
}

export function useRejectProposal() {
  const refresh = useRefreshLearning()
  return useMutation({
    mutationFn: ({ id, decision }: { id: string; decision: Decision }) =>
      apiPost<{ rejected: boolean }>(`/state/learning/proposals/${id}/reject`, decision),
    onSuccess: refresh,
  })
}

export function useRevertRulebook() {
  const refresh = useRefreshLearning()
  return useMutation({
    mutationFn: (decision: Decision) =>
      apiPost<{ reverted: boolean; version: string; source: string; note?: string }>('/state/learning/active/revert', { ...decision, confirm: true }),
    onSuccess: refresh,
  })
}

export function useGenerateProposal() {
  const refresh = useRefreshLearning()
  return useMutation({
    mutationFn: ({ requestedBy, horizon }: { requestedBy: string; horizon: number }) =>
      apiPost<GenerateResponse>('/state/learning/proposals/generate', { requested_by: requestedBy, horizon_minutes: horizon }),
    onSuccess: refresh,
  })
}
