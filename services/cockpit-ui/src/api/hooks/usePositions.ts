import { useQuery } from '@tanstack/react-query'
import { apiGet } from '../client'
import type { Position } from '../types'

export function usePositions(venue = 'all') {
  return useQuery({
    queryKey: ['positions', venue],
    queryFn: () => apiGet<Position[]>(`/state/positions?venue=${venue}`),
    refetchInterval: 10000,
  })
}
