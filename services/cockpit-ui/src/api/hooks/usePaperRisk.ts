import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPost } from '../client'
import type { Account, Audited, LimitValues, Reconciliation, RiskState } from '../paperRiskTypes'

/** Paper risk readings and the audited actions that change them. Every action names its operator and reason. */

const RISK = ['paper-risk']
const ACCOUNT = ['paper-account']
const RECONCILIATION = ['paper-reconciliation']
// The managed paper panel reads these; a pause or kill changes what it shows.
const DEPENDENT = [['paper-control'], ['managed-paper']]

export function usePaperRiskState() {
  return useQuery({ queryKey: RISK, queryFn: () => apiGet<RiskState>('/state/paper-risk'), refetchInterval: 15000 })
}

export function usePaperAccount() {
  return useQuery({ queryKey: ACCOUNT, queryFn: () => apiGet<Account>('/state/paper-account'), refetchInterval: 15000 })
}

export function usePaperReconciliation() {
  return useQuery({ queryKey: RECONCILIATION, queryFn: () => apiGet<Reconciliation>('/state/paper-reconciliation'), refetchInterval: 60000 })
}

export function usePaperRiskActions() {
  const qc = useQueryClient()
  const refresh = () => Promise.all([RISK, ACCOUNT, RECONCILIATION, ...DEPENDENT].map((queryKey) => qc.invalidateQueries({ queryKey })))
  const pause = useMutation({
    mutationFn: (body: Audited & { entries_paused: boolean }) => apiPost('/state/paper-pause', body),
    onSettled: refresh,
  })
  const kill = useMutation({
    mutationFn: (body: Audited) => apiPost<{ closed: unknown[]; pending: unknown[] }>('/state/paper-kill', { ...body, confirm: true }),
    onSettled: refresh,
  })
  const resume = useMutation({
    mutationFn: (body: Audited) => apiPost('/state/paper-kill/resume', { ...body, confirm: true }),
    onSettled: refresh,
  })
  const limits = useMutation({
    mutationFn: (body: Audited & Partial<LimitValues>) => apiPost('/state/paper-limits', body),
    onSettled: refresh,
  })
  return { pause, kill, resume, limits, refresh }
}
