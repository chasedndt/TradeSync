import { test } from 'node:test'
import assert from 'node:assert/strict'
import { importTs } from './support/importTs.mjs'

const format = await importTs('src/components/ledger/paperRisk/paperRiskFormat.ts')
const field = Object.fromEntries(format.LIMIT_FIELDS.map((f) => [f.key, f]))

test('money and percentages read as the panel shows them', () => {
  assert.equal(format.usd(1234.5), '1,234.50 USDC')
  assert.equal(format.signedUsd(-250), '−250.00 USDC')
  assert.equal(format.signedUsd(12.5), '+12.50 USDC')
  assert.equal(format.usd(null), '—')
  assert.equal(format.usd(Number.NaN), '—')
  assert.equal(format.percent(0.0612), '6.12%')
})

test('meters are comfortable below three quarters, warn up to the limit, and breach at it', () => {
  assert.equal(format.meterTone(0.5), 'good')
  assert.equal(format.meterTone(0.8), 'warn')
  assert.equal(format.meterTone(1), 'bad')
  assert.equal(format.meterTone(null), 'dim')
  assert.equal(format.meterWidth(1.7), '100%')
  assert.equal(format.meterWidth(-1), '0%')
  assert.equal(format.meterWidth(0.256), '26%')
})

test('readings carry an exact UTC time and ages read plainly', () => {
  assert.equal(format.utcStamp(0), '1970-01-01 00:00:00 UTC')
  assert.equal(format.utcStamp('2026-09-15T10:00:05.123+00:00'), '2026-09-15 10:00:05 UTC')
  assert.equal(format.utcStamp(null), '—')
  assert.equal(format.ageText(45), '45s')
  assert.equal(format.ageText(250), '4m 10s')
  assert.equal(format.ageText(7500), '2h 5m')
})

test('reason codes read as words', () => {
  assert.equal(format.codeLabel('DAILY_LOSS_LIMIT'), 'Daily loss limit')
})

test('limit inputs take percentages, stay in range and never send a partial number', () => {
  assert.equal(format.LIMIT_FIELDS.length, 9)
  assert.equal(format.parseLimit(field.max_drawdown_fraction, '6'), 0.06)
  assert.equal(format.parseLimit(field.max_drawdown_fraction, '100'), null)
  assert.equal(format.parseLimit(field.max_concurrent_positions, '2.5'), null)
  assert.equal(format.parseLimit(field.daily_loss_limit_usdc, ''), null)
  assert.equal(format.parseLimit(field.correlation_threshold, '0.7'), 0.7)
  assert.equal(format.inputValue(field.max_symbol_exposure_fraction, 0.12), '12')
  assert.equal(format.limitText(field.max_entry_quote_age_s, 15), '15s')
})
