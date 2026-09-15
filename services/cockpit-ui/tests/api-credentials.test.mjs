import { test, beforeEach } from 'node:test'
import assert from 'node:assert/strict'
import { readFile, readdir } from 'node:fs/promises'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import { importTs } from './support/importTs.mjs'

// Credentials the Cockpit sends to state-api: kept for the browser session only, sent only in
// their own headers, never compiled into the build, and never sent to a host other than this
// site or loopback.

class MemoryStorage {
  #entries = new Map()
  getItem(key) { return this.#entries.has(key) ? this.#entries.get(key) : null }
  setItem(key, value) { this.#entries.set(key, String(value)) }
  removeItem(key) { this.#entries.delete(key) }
}

const install = (name, value) => Object.defineProperty(globalThis, name, { value, configurable: true, writable: true })
const refuse = (name) => Object.defineProperty(globalThis, name, { get() { throw new Error('storage blocked') }, configurable: true })

const credentials = await importTs('src/api/credentials.ts')
const client = await importTs('src/api/client.ts')
const TOKEN = 't'.repeat(40)
const JSON_ONLY = { 'Content-Type': 'application/json' }
let requests = []

beforeEach(() => {
  install('sessionStorage', new MemoryStorage())
  install('localStorage', new MemoryStorage())
  requests = []
  install('fetch', async (url, init) => {
    requests.push({ url, method: init?.method ?? 'GET', headers: init?.headers })
    return { ok: true, json: async () => ({}) }
  })
})

test('credentials last for the browser session and are never written to lasting storage', () => {
  credentials.setOperatorToken(` ${TOKEN} `)
  credentials.setMobileControlKey('mobile-control-key')
  assert.equal(sessionStorage.getItem('tradesync_operator_token'), TOKEN)
  assert.equal(sessionStorage.getItem('apiKey'), 'mobile-control-key')
  assert.equal(localStorage.getItem('tradesync_operator_token'), null)
  assert.equal(localStorage.getItem('apiKey'), null)
})

test('a key an earlier build left in localStorage moves into the session and off disk', () => {
  localStorage.setItem('apiKey', 'key-from-an-earlier-build')
  assert.equal(credentials.getMobileControlKey(), 'key-from-an-earlier-build')
  assert.equal(localStorage.getItem('apiKey'), null)
  assert.equal(sessionStorage.getItem('apiKey'), 'key-from-an-earlier-build')
  credentials.clearMobileControlKey()
  assert.equal(credentials.getMobileControlKey(), null)
})

test('each credential travels only in its own header, and only once entered', async () => {
  await client.apiPost('/state/paper-control', {})
  assert.deepEqual(requests[0].headers, JSON_ONLY)

  credentials.setOperatorToken(TOKEN)
  credentials.setMobileControlKey('mobile-control-key')
  await client.apiGet('/state/access-policy')
  assert.equal(requests[1].url, '/api/state/access-policy')
  assert.deepEqual(requests[1].headers, { ...JSON_ONLY, 'X-Operator-Token': TOKEN, 'X-API-Key': 'mobile-control-key' })

  credentials.clearOperatorToken()
  credentials.clearMobileControlKey()
  await client.apiDelete('/state/canvas/drawings/1')
  assert.deepEqual(requests[2].headers, JSON_ONLY)
})

test('storage the browser refuses leaves requests working, without credentials', async () => {
  refuse('sessionStorage')
  refuse('localStorage')
  credentials.setOperatorToken(TOKEN)
  assert.deepEqual(credentials.credentialHeaders(), {})
  assert.equal(client.getApiBaseUrl(), '/api')
  await client.apiGet('/state/health')
  assert.equal(requests[0].url, '/api/state/health')
})

test('a base URL can only point at this site or a loopback address', () => {
  const cases = {
    '': '/api',
    '/': '/api',
    '/api/': '/api',
    'http://127.0.0.1:8000': 'http://127.0.0.1:8000',
    'http://localhost:8000/': 'http://localhost:8000',
    'http://[::1]:8000': 'http://[::1]:8000',
    'https://collector.example.invalid': '/api',
    '//collector.example.invalid': '/api',
    '/\\collector.example.invalid': '/api',
    'http://127.0.0.1@collector.example.invalid': '/api',
    'http://localhost.collector.example.invalid': '/api',
    'javascript:alert(1)': '/api',
    'api': '/api',
  }
  for (const [input, expected] of Object.entries(cases)) assert.equal(credentials.safeApiBaseUrl(input), expected, input)
})

test('a base URL that would be ignored is not stored, and a stored one is checked again on use', () => {
  assert.equal(client.setApiBaseUrl('https://collector.example.invalid'), '/api')
  assert.equal(localStorage.getItem('apiBaseUrl'), null)
  assert.equal(client.setApiBaseUrl('http://127.0.0.1:8000/'), 'http://127.0.0.1:8000')
  assert.equal(client.getApiBaseUrl(), 'http://127.0.0.1:8000')
  localStorage.setItem('apiBaseUrl', '//collector.example.invalid')
  assert.equal(client.getApiBaseUrl(), '/api')
})

const SRC = fileURLToPath(new URL('../src/', import.meta.url))
const BUILD_FLAGS = new Set(['DEV', 'PROD', 'MODE', 'BASE_URL', 'SSR'])

async function sourceFiles(dir) {
  const files = []
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name)
    if (entry.isDirectory()) files.push(...(await sourceFiles(path)))
    else if (/\.(tsx?|jsx?)$/.test(entry.name) && !entry.name.endsWith('.d.ts')) files.push(path)
  }
  return files
}

test('no source file compiles a build-time environment value into the Cockpit bundle', async () => {
  const offenders = []
  for (const path of await sourceFiles(SRC)) {
    const text = await readFile(path, 'utf8')
    for (const match of text.matchAll(/import\.meta\.env(?:\.([A-Za-z_][A-Za-z0-9_]*))?/g)) {
      if (!BUILD_FLAGS.has(match[1])) offenders.push(`${relative(SRC, path)}: ${match[0]}`)
    }
  }
  assert.deepEqual(offenders, [])
})
