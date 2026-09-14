const DEFAULT_BASE_URL = '/api'

export function getApiBaseUrl(): string {
  return localStorage.getItem('apiBaseUrl') || DEFAULT_BASE_URL
}

export function setApiBaseUrl(url: string): void {
  localStorage.setItem('apiBaseUrl', url)
}

function getApiKey(): string | null {
  return localStorage.getItem('apiKey') || import.meta.env.VITE_API_KEY || null
}

function getHeaders(): HeadersInit {
  const headers: HeadersInit = { 'Content-Type': 'application/json' }
  const apiKey = getApiKey()
  if (apiKey) headers['X-API-Key'] = apiKey
  return headers
}

/** A failed request: the server's own explanation as the message, and the HTTP status. */
export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/**
 * FastAPI's `detail` as a sentence: a string as it is, a validation list as
 * "field: problem" pairs, anything else as JSON. Null when there is nothing to say.
 */
export function describeDetail(detail: unknown): string | null {
  if (typeof detail === 'string') return detail.trim() || null
  if (Array.isArray(detail)) {
    const parts = detail
      .map((issue) => {
        if (typeof issue === 'string') return issue
        if (!issue || typeof issue.msg !== 'string') return null
        const path = Array.isArray(issue.loc)
          ? issue.loc.filter((part: unknown) => part !== 'body' && part !== 'query').join('.')
          : ''
        return path ? `${path}: ${issue.msg}` : issue.msg
      })
      .filter((part): part is string => Boolean(part))
    return parts.length ? parts.join('; ') : null
  }
  if (detail && typeof detail === 'object') return JSON.stringify(detail)
  return null
}

async function responseError(res: Response): Promise<ApiError> {
  let detail: string | null = null
  try {
    detail = describeDetail((await res.json())?.detail)
  } catch {
    // Not JSON: the status line is all there is.
  }
  const status = `${res.status}${res.statusText ? ` ${res.statusText}` : ''}`
  return new ApiError(detail ? `${detail} (HTTP ${res.status})` : `The server answered ${status} without a reason`, res.status)
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${getApiBaseUrl()}${path}`, { headers: getHeaders() })
  if (!res.ok) throw await responseError(res)
  return res.json()
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${getApiBaseUrl()}${path}`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify(body),
  })
  if (!res.ok) throw await responseError(res)
  return res.json()
}

export async function apiDelete<T>(path: string): Promise<T> {
  const res = await fetch(`${getApiBaseUrl()}${path}`, {
    method: 'DELETE',
    headers: getHeaders(),
  })
  if (!res.ok) throw await responseError(res)
  return res.json()
}

export function setApiKey(key: string): void {
  localStorage.setItem('apiKey', key)
}

export function clearApiKey(): void {
  localStorage.removeItem('apiKey')
}
