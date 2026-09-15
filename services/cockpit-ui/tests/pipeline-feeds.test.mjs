import { test } from 'node:test'
import assert from 'node:assert/strict'
import { importTs } from './support/importTs.mjs'

const { ago, countsLine, deliveryLabel, feedTone, lastDelivery, stateLabel } = await importTs('src/components/pipeline/feedText.ts')

test('a feed reads good only while connected or answering', () => {
  assert.equal(feedTone({ state: 'connected' }), 'good')
  assert.equal(feedTone({ state: 'ok' }), 'good')
  assert.equal(feedTone({ state: 'connecting' }), 'warn')
  assert.equal(feedTone({ state: 'not_started' }), 'warn')
  assert.equal(feedTone({ state: 'disconnected' }), 'bad')
  assert.equal(feedTone({ state: 'provider_access_denied' }), 'bad')
  assert.equal(stateLabel({ state: 'provider_access_denied', kind: 'websocket' }), 'provider access denied')
  assert.equal(stateLabel({ state: 'ok', kind: 'loop' }), 'running')
  assert.equal(stateLabel({ state: 'ok', kind: 'fetch' }), 'answering')
})

test('a stream is judged by its last message, a fetch or loop by its last success', () => {
  const at = { last_message_at: '2026-09-15T01:00:00Z', last_success_at: '2026-09-15T00:59:00Z' }
  assert.equal(lastDelivery({ kind: 'websocket', ...at }), at.last_message_at)
  assert.equal(lastDelivery({ kind: 'fetch', ...at }), at.last_success_at)
  assert.equal(lastDelivery({ kind: 'loop', ...at }), at.last_success_at)
  assert.equal(deliveryLabel({ kind: 'route' }), 'last successful fetch')
  assert.equal(deliveryLabel({ kind: 'loop' }), 'last pass')
  assert.equal(ago('2026-09-15T01:00:00Z', Date.parse('2026-09-15T01:05:30Z')), '5m ago')
  assert.equal(ago('2026-09-15T01:00:00Z', Date.parse('2026-09-15T00:59:00Z')), '0s ago')
  assert.equal(ago(null, 0), '—')
})

test('counts read as plain words, singular where there is one', () => {
  assert.equal(countsLine({ messages: 3412, events: 1 }), '3,412 messages · 1 event stored')
  assert.equal(countsLine({ passes: 60, map_passes: 12 }), '60 passes · 12 map passes')
  assert.equal(countsLine({}), 'nothing counted')
})
