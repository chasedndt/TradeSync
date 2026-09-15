import { test } from 'node:test'
import assert from 'node:assert/strict'
import { importTs } from './support/importTs.mjs'

const { bytes, duration, elapsedSeconds, fireLine, laterRunsLine, outputDelivery, runTone, span } = await importTs('src/pages/fleetActivityText.ts')

test('spans, durations and sizes read plainly', () => {
  assert.equal(span(45), '45s')
  assert.equal(span(240), '4m')
  assert.equal(span(7500), '2h 5m')
  assert.equal(span(273600), '3d 4h')
  assert.equal(span(null), '—')
  assert.equal(duration(850), '850 ms')
  assert.equal(duration(40_000), '40.0s')
  assert.equal(duration(120_000), '2m')
  assert.equal(duration(null), '—')
  assert.equal(bytes(512), '512 B')
  assert.equal(bytes(3628), '3.5 KB')
})

test('a running run counts from its start, or from its claim when it has not started', () => {
  const now = Date.parse('2026-09-15T01:10:00Z')
  assert.equal(elapsedSeconds({ started_at: '2026-09-15T01:06:00Z', claimed_at: '2026-09-15T01:05:00Z' }, now), 240)
  assert.equal(elapsedSeconds({ started_at: null, claimed_at: '2026-09-15T01:05:00Z' }, now), 300)
  assert.equal(elapsedSeconds({ started_at: null, claimed_at: null }, now), null)
})

test('a model call reads as failed, silent or delivered, and a script job as making none', () => {
  assert.equal(fireLine(null), 'no model call recorded (script jobs make none)')
  assert.equal(fireLine({ silent: true, deliver_target: 'local', error: null }), 'silent: nothing delivered')
  assert.equal(fireLine({ silent: false, deliver_target: 'discord:1517902266332348490', error: null }), 'delivered to Discord')
  assert.equal(fireLine({ silent: false, deliver_target: 'local', error: 'RuntimeError: HTTP 402' }), 'model call failed: RuntimeError: HTTP 402')
})

test('an output names where it went, and later runs without a stored output are explained', () => {
  const output = { delivery: { kind: 'discord', channel_label: 'thesis-desk' } }
  assert.equal(outputDelivery(output), 'Discord #thesis-desk')
  assert.equal(outputDelivery({ delivery: { kind: 'local', channel_label: null } }), 'TradeSync only')
  assert.equal(laterRunsLine({ latest_output: output, later_runs_without_output: 2 }), '2 later runs left no stored output: silent runs are not stored.')
  assert.equal(laterRunsLine({ latest_output: output, later_runs_without_output: 0 }), null)
  assert.equal(runTone('completed'), 'tone-good')
  assert.equal(runTone('failed'), 'tone-bad')
  assert.equal(runTone('unknown'), 'tone-warn')
  assert.equal(runTone(null), 'tone-dim')
})
