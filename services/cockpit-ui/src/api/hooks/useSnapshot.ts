import { useQuery } from '@tanstack/react-query'
import { apiGet } from '../client'
import type { SnapshotResponse } from '../types'

export function useSnapshot() {
  return useQuery({
    queryKey: ['snapshot'],
    queryFn: () => apiGet<SnapshotResponse>('/state/snapshot'),
    refetchInterval: 5000,
  })
}
