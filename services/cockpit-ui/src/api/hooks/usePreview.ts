import { useMutation, useQueryClient } from '@tanstack/react-query'
import { apiPost } from '../client'
import type { PreviewRequest, PreviewResponse } from '../types'

export function usePreview() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (req: PreviewRequest) => apiPost<PreviewResponse>('/actions/preview', req),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['opportunities'] })
    },
  })
}
