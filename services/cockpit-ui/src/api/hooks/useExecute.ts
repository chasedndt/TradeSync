import { useMutation, useQueryClient } from '@tanstack/react-query'
import { apiPost } from '../client'
import type { ExecuteRequest, ExecutionResult } from '../types'

export function useExecute() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (req: ExecuteRequest) => apiPost<ExecutionResult>('/actions/execute', req),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['opportunities'] })
      queryClient.invalidateQueries({ queryKey: ['positions'] })
      queryClient.invalidateQueries({ queryKey: ['execution-status'] })
    },
  })
}
