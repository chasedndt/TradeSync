import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../client'

export interface MacroHeadline {
  title: string
  source: string
  category: string
  url: string
  published_at?: string
  summary?: string
  sentiment?: 'bullish' | 'bearish' | 'neutral'
}

export interface MacroFeedResponse {
  headlines: MacroHeadline[]
  status: {
    sources_configured: number
    headlines_cached: number
    cache_age_seconds?: number
    cache_ttl_seconds: number
    sources: string[]
    error?: string
  }
  cached: boolean
  ts: string
}

export function useMacroHeadlines(options?: {
  refresh?: boolean
  limit?: number
  category?: string
}) {
  return useQuery<MacroFeedResponse>({
    queryKey: ['macro-headlines', options?.category, options?.limit],
    queryFn: async () => {
      const params = new URLSearchParams()
      if (options?.refresh) params.append('refresh', 'true')
      if (options?.limit) params.append('limit', String(options.limit))
      if (options?.category) params.append('category', options.category)

      const url = `/state/macro/headlines${params.toString() ? '?' + params.toString() : ''}`
      const response = await apiClient.get<MacroFeedResponse>(url)
      return response.data
    },
    refetchInterval: 60000, // Refetch every minute
    staleTime: 30000, // Consider data stale after 30 seconds
  })
}

export function useMacroStatus() {
  return useQuery({
    queryKey: ['macro-status'],
    queryFn: async () => {
      const response = await apiClient.get('/state/macro/status')
      return response.data
    },
    refetchInterval: 300000, // Refetch every 5 minutes
  })
}
