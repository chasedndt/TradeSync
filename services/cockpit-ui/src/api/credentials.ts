const DEFAULT_BASE_URL = '/api'

export function getApiBaseUrl(): string {
  return localStorage.getItem('apiBaseUrl') || DEFAULT_BASE_URL
}

export function setApiBaseUrl(url: string): void {
  localStorage.setItem('apiBaseUrl', url)
}

export function getApiKey(): string | null {
  return localStorage.getItem('apiKey') || import.meta.env.VITE_API_KEY || null
}

export function setApiKey(key: string): void {
  localStorage.setItem('apiKey', key)
}

export function clearApiKey(): void {
  localStorage.removeItem('apiKey')
}
