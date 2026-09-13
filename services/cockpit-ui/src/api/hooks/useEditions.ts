import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPost } from '../client'
import type { ThesisEdition, ThesisEditionsResponse } from '../types'

/** Recent thesis editions, newest first, and the schedule that produces them. */
export function useEditions(limit = 10) {
  return useQuery({
    queryKey: ['thesis-editions', limit],
    queryFn: () => apiGet<ThesisEditionsResponse>(`/state/thesis/editions?limit=${limit}`),
    refetchInterval: 60_000,
    retry: 1,
  })
}

export function useEdition(id: string | null) {
  return useQuery({
    queryKey: ['thesis-edition', id],
    queryFn: () => apiGet<ThesisEdition>(`/state/thesis/editions/${id}`),
    enabled: Boolean(id),
    retry: 1,
  })
}

/** Ask for an edition now. It assembles every symbol's thesis, so it takes a minute or two. */
export function useGenerateEdition() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => apiPost<ThesisEdition>('/state/thesis/editions/generate?edition=manual', {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['thesis-editions'] }),
  })
}
