import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPost, apiDelete } from '../client'
import type { DrawingList, Drawing, DrawingInput } from '../types'

export function useDrawings(symbol: string, interval: string) {
  return useQuery({
    queryKey: ['drawings', symbol, interval],
    queryFn: () =>
      apiGet<DrawingList>(
        `/state/canvas/drawings?symbol=${encodeURIComponent(symbol)}` +
          `&interval=${encodeURIComponent(interval)}`,
      ),
    refetchInterval: 30_000,
  })
}

export function useCreateDrawing() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: DrawingInput) =>
      apiPost<Drawing>('/state/canvas/drawings', input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['drawings'] }),
  })
}

export function useDeleteDrawing() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (drawingId: string) =>
      apiDelete<{ deleted: boolean }>(`/state/canvas/drawings/${drawingId}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['drawings'] }),
  })
}
