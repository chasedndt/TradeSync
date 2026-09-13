import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPost } from '../client'
import type { EditionGeneration, ThesisEdition, ThesisEditionsResponse } from '../types'

/** Recent editions, newest first, the schedule, and any regeneration under way (polled faster while it runs). */
export function useEditions(limit = 10) {
  return useQuery({
    queryKey: ['thesis-editions', limit],
    queryFn: () => apiGet<ThesisEditionsResponse>(`/state/thesis/editions?limit=${limit}`),
    refetchInterval: (query) => (query.state.data?.generation?.running ? 4_000 : 60_000),
    retry: 1,
  })
}

export function useEdition(id: string | null) {
  return useQuery({
    queryKey: ['thesis-edition', id],
    queryFn: () => apiGet<ThesisEdition>(`/state/thesis/editions/${id}`),
    enabled: Boolean(id),
    staleTime: 60_000,
    retry: 1,
  })
}

/** Start a regeneration. It runs in the background; the editions list reports its stage. */
export function useGenerateEdition() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (reason: string) =>
      apiPost<{ status: string; generation: EditionGeneration }>(
        `/state/thesis/editions/generate?edition=manual&reason=${encodeURIComponent(reason.slice(0, 200))}`,
        {},
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['thesis-editions'] }),
  })
}
