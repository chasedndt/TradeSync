/**
 * What the Cockpit sends to state-api with each request, and where it keeps it.
 *
 * Two credentials, both entered by the operator in Settings, neither compiled into the build:
 *
 * - the operator token, sent as X-Operator-Token. state-api requires it on every change when
 *   STATE_API_OPERATOR_TOKEN is set; GET /state/access-policy says whether it is.
 * - the mobile alert control key, sent as X-API-Key. Only the mobile alert controls check it.
 *
 * Both are kept in sessionStorage, so they last for this browser session and are not left on
 * disk for whoever opens this browser profile later. Earlier builds kept the key in localStorage;
 * it is moved into the session on first read and the stored copy removed.
 *
 * The API base URL is not a secret and stays in localStorage, but only a path on this site or a
 * loopback address is honoured, so a stored value cannot send either credential to another host.
 */

export const DEFAULT_BASE_URL = '/api'
export const OPERATOR_TOKEN_HEADER = 'X-Operator-Token'
export const MOBILE_CONTROL_KEY_HEADER = 'X-API-Key'

const BASE_URL_KEY = 'apiBaseUrl'
const MOBILE_CONTROL_KEY = 'apiKey'
const OPERATOR_TOKEN_KEY = 'tradesync_operator_token'
const LOOPBACK_HOSTS = new Set(['127.0.0.1', 'localhost', '[::1]'])
const THIS_SITE = 'http://cockpit.invalid'

type Area = 'sessionStorage' | 'localStorage'

/** Browsers can refuse storage outright (blocked site data, some private windows), so every access is guarded. */
function read(area: Area, key: string): string | null {
  try {
    return globalThis[area].getItem(key)
  } catch {
    return null
  }
}

function write(area: Area, key: string, value: string | null): void {
  try {
    if (value) globalThis[area].setItem(key, value)
    else globalThis[area].removeItem(key)
  } catch {
    // Storage refused: the value is simply not kept.
  }
}

function sessionCredential(key: string): string | null {
  const legacy = read('localStorage', key)
  if (legacy !== null) {
    write('localStorage', key, null)
    if (!read('sessionStorage', key) && legacy.trim()) write('sessionStorage', key, legacy.trim())
  }
  return read('sessionStorage', key)?.trim() || null
}

export const getOperatorToken = (): string | null => sessionCredential(OPERATOR_TOKEN_KEY)

export function setOperatorToken(token: string): void {
  write('sessionStorage', OPERATOR_TOKEN_KEY, token.trim() || null)
}

export function clearOperatorToken(): void {
  write('sessionStorage', OPERATOR_TOKEN_KEY, null)
}

export const getMobileControlKey = (): string | null => sessionCredential(MOBILE_CONTROL_KEY)

export function setMobileControlKey(key: string): void {
  write('sessionStorage', MOBILE_CONTROL_KEY, key.trim() || null)
}

export function clearMobileControlKey(): void {
  write('sessionStorage', MOBILE_CONTROL_KEY, null)
  write('localStorage', MOBILE_CONTROL_KEY, null)
}

/** The credential headers for a request: only those the operator has entered this session. */
export function credentialHeaders(): Record<string, string> {
  const headers: Record<string, string> = {}
  const token = getOperatorToken()
  const key = getMobileControlKey()
  if (token) headers[OPERATOR_TOKEN_HEADER] = token
  if (key) headers[MOBILE_CONTROL_KEY_HEADER] = key
  return headers
}

/** A base URL the Cockpit may send credentials to: a path on this site or a loopback address, otherwise the default. */
export function safeApiBaseUrl(value: string | null | undefined): string {
  const candidate = (value ?? '').trim().replace(/\/+$/, '')
  if (!candidate) return DEFAULT_BASE_URL
  try {
    const url = new URL(candidate, THIS_SITE)
    if (candidate.startsWith('/')) return url.origin === THIS_SITE ? candidate : DEFAULT_BASE_URL
    const web = url.protocol === 'http:' || url.protocol === 'https:'
    return web && LOOPBACK_HOSTS.has(url.hostname) ? candidate : DEFAULT_BASE_URL
  } catch {
    return DEFAULT_BASE_URL
  }
}

export const getApiBaseUrl = (): string => safeApiBaseUrl(read('localStorage', BASE_URL_KEY))

/** Keep the base URL the Cockpit will actually use and return it; an unusable value is not stored. */
export function setApiBaseUrl(url: string): string {
  const usable = safeApiBaseUrl(url)
  write('localStorage', BASE_URL_KEY, usable === DEFAULT_BASE_URL ? null : usable)
  return usable
}
