import { credentialHeaders, getApiBaseUrl } from './credentials'

// Views that build URLs themselves (chart images, Settings) read the base URL through the client.
export { getApiBaseUrl, setApiBaseUrl } from './credentials'

function getHeaders(): HeadersInit {
  // Only what the operator entered this session; nothing is compiled into the build.
  return { 'Content-Type': 'application/json', ...credentialHeaders() }
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

export async function apiPut<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${getApiBaseUrl()}${path}`, {
    method: 'PUT',
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
