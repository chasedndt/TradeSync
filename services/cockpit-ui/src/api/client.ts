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

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${getApiBaseUrl()}${path}`, { headers: getHeaders() })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${getApiBaseUrl()}${path}`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

export function setApiKey(key: string): void {
  localStorage.setItem('apiKey', key)
}

export function clearApiKey(): void {
  localStorage.removeItem('apiKey')
}
