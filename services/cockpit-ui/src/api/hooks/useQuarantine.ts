import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPost } from '../client'
import type { QuarantineList, QuarantineReviewResult } from '../types'

export function useQuarantine(pendingOnly = false, limit = 50) {
  return useQuery({
    queryKey: ['quarantine', pendingOnly, limit],
    queryFn: () =>
      apiGet<QuarantineList>(
        `/state/quarantine?pending_only=${pendingOnly}&limit=${limit}`,
      ),
    refetchInterval: 15_000,
  })
}

export function useReviewQuarantineItem() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, reviewedBy, promote, targetProvenance }: {
      id: string
      reviewedBy: string
      promote: boolean
      targetProvenance: string
    }) =>
      apiPost<QuarantineReviewResult>(`/state/quarantine/${id}/review`, {
        reviewed_by: reviewedBy,
        promote,
        target_provenance: targetProvenance,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['quarantine'] })
    },
  })
}
