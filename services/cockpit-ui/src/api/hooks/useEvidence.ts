import { useQuery } from '@tanstack/react-query'
import { apiGet } from '../client'
import type { EvidenceResponse } from '../types'

export function useEvidence(opportunityId: string | undefined) {
  return useQuery({
    queryKey: ['evidence', opportunityId],
    queryFn: () => apiGet<EvidenceResponse>(`/state/evidence?opportunity_id=${opportunityId}`),
    enabled: !!opportunityId,
  })
}
