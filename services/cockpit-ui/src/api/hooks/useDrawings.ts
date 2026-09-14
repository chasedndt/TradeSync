import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { apiDelete, apiGet, apiPost, apiPut } from '../client'
import type { Drawing, DrawingInput, DrawingList } from '../drawingTypes'
import { pendingDrawingId, withDrawing, withEdit, withoutDrawing } from './drawingCache'

/** Drawings are anchored in time and price, so the canvas reads a symbol's drawings from every interval. */
export function drawingsKey(symbol: string) {
  return ['drawings', symbol, 'all-intervals'] as const
}

export function useDrawings(symbol: string) {
  return useQuery({
    queryKey: drawingsKey(symbol),
    queryFn: () =>
      apiGet<DrawingList>(`/state/canvas/drawings?symbol=${encodeURIComponent(symbol)}&all_intervals=true`),
    refetchInterval: 30_000,
  })
}

interface Snapshot {
  symbol: string
  previous: DrawingList | undefined
}

/** Stop an in-flight read overwriting an optimistic change, and keep what to roll back to. */
async function hold(client: QueryClient, symbol: string): Promise<Snapshot> {
  await client.cancelQueries({ queryKey: drawingsKey(symbol) })
  return { symbol, previous: client.getQueryData<DrawingList>(drawingsKey(symbol)) }
}

function change(client: QueryClient, symbol: string, update: (list: DrawingList | undefined) => DrawingList | undefined) {
  client.setQueryData<DrawingList>(drawingsKey(symbol), update)
}

function rollBack(client: QueryClient, snapshot: Snapshot | undefined) {
  if (snapshot) client.setQueryData(drawingsKey(snapshot.symbol), snapshot.previous)
}

function settle(client: QueryClient, symbol: string) {
  return client.invalidateQueries({ queryKey: drawingsKey(symbol) })
}

export function useCreateDrawing() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (input: DrawingInput) => apiPost<Drawing>('/state/canvas/drawings', input),
    onMutate: async (input) => {
      const snapshot = await hold(client, input.symbol)
      // Drawn straight away, then replaced by the stored drawing when it returns.
      const pending: Drawing = { ...input, drawing_id: pendingDrawingId(), version: 0 }
      change(client, input.symbol, (list) => withDrawing(list, pending))
      return { ...snapshot, pendingId: pending.drawing_id }
    },
    onSuccess: (created, input, context) =>
      change(client, input.symbol, (list) => withDrawing(withoutDrawing(list, context?.pendingId ?? ''), created)),
    onError: (_error, input, context) =>
      change(client, input.symbol, (list) => withoutDrawing(list, context?.pendingId ?? '')),
    onSettled: (_data, _error, input) => settle(client, input.symbol),
  })
}

/** Records a new version of a drawing; the previous version is kept server-side. */
export function useUpdateDrawing() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ drawingId, input }: { drawingId: string; input: DrawingInput }) =>
      apiPut<Drawing>(`/state/canvas/drawings/${drawingId}`, input),
    onMutate: async ({ drawingId, input }) => {
      const snapshot = await hold(client, input.symbol)
      change(client, input.symbol, (list) => withEdit(list, drawingId, input))
      return snapshot
    },
    onError: (_error, _variables, snapshot) => rollBack(client, snapshot),
    onSettled: (_data, _error, { input }) => settle(client, input.symbol),
  })
}

export function useDeleteDrawing() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ drawingId }: { symbol: string; drawingId: string }) =>
      apiDelete<{ deleted: boolean }>(`/state/canvas/drawings/${drawingId}`),
    onMutate: async ({ symbol, drawingId }) => {
      const snapshot = await hold(client, symbol)
      change(client, symbol, (list) => withoutDrawing(list, drawingId))
      return snapshot
    },
    onError: (_error, _variables, snapshot) => rollBack(client, snapshot),
    onSettled: (_data, _error, { symbol }) => settle(client, symbol),
  })
}

/** Removes every drawing for a symbol, on every interval. Each keeps its stored history. */
export function useClearDrawings() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (symbol: string) =>
      apiDelete<{ symbol: string; deleted: number }>(`/state/canvas/drawings?symbol=${encodeURIComponent(symbol)}`),
    onMutate: async (symbol) => {
      const snapshot = await hold(client, symbol)
      change(client, symbol, (list) => (list ? { ...list, drawings: [] } : list))
      return snapshot
    },
    onError: (_error, _symbol, snapshot) => rollBack(client, snapshot),
    onSettled: (_data, _error, symbol) => settle(client, symbol),
  })
}
