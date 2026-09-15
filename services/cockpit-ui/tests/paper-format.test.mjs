import { test } from 'node:test'
import assert from 'node:assert/strict'
import { importTs } from './support/importTs.mjs'

const { age, bps, duration, exactTime, pct, price, usdc, words } = await importTs('src/components/ledger/paper/paperFormat.ts')

test('ages read in their two largest units', () => {
  assert.equal(age(4.25), '4.3 s')
  assert.equal(age(42), '42 s')
  assert.equal(age(185), '3 min 5 s')
  assert.equal(age(7440), '2 h 4 min')
  assert.equal(age(522000), '6 d 1 h')
  assert.equal(age(-42), '42 s')
  assert.equal(age(null), '—')
})

test('holding times read the way the rules declare them', () => {
  assert.equal(duration(10800), '3 h')
  assert.equal(duration(86400), '24 h')
  assert.equal(duration(604800), '7 days')
})

test('costs keep cents and their sign, and names read as words', () => {
  assert.equal(usdc(0.1125), '0.1125 USDC')
  assert.equal(usdc(-2.5), '−2.50 USDC')
  assert.equal(usdc(-0.00001), '0.0000 USDC')
  assert.equal(usdc(undefined), '—')
  assert.equal(bps(1.234), '1.23 bps')
  assert.equal(pct(0.00045), '0.045%')
  assert.equal(words('trailing_stop'), 'trailing stop')
  assert.equal(price(Number.NaN), '—')
  assert.equal(exactTime(null), 'unknown')
})
