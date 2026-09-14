import { test } from 'node:test'
import assert from 'node:assert/strict'
import { importTs } from './support/importTs.mjs'

const { timeToLogical, logicalToTime } = await importTs('src/components/canvas/drawing/anchors.ts')

const T = 1_788_800_000
const axis = { times: [T, T + 900, T + 1800, T + 2700], step: 900 }

test('each bar time maps to its own logical index', () => {
  assert.deepEqual(axis.times.map((time) => timeToLogical(time, axis)), [0, 1, 2, 3])
})

test('a time between two bars sits between their indices', () => {
  assert.equal(timeToLogical(T + 450, axis), 0.5)
  assert.equal(logicalToTime(2.25, axis), T + 1800 + 225)
})

test('past the last candle the index keeps counting in bars of the interval', () => {
  assert.equal(timeToLogical(T + 2700 + 1800, axis), 5)
  assert.equal(logicalToTime(5.5, axis), T + 2700 + 2.5 * 900)
})

test('before the first candle the index runs negative the same way', () => {
  assert.equal(timeToLogical(T - 900, axis), -1)
  assert.equal(logicalToTime(-2, axis), T - 1800)
})

test('conversion round-trips inside and beyond the data', () => {
  for (const logical of [-3.25, 0, 1.5, 3, 7.75]) {
    const back = timeToLogical(logicalToTime(logical, axis), axis)
    assert.ok(Math.abs(back - logical) < 1e-9, `${logical} came back as ${back}`)
  }
})

test('a gap in the bars is spanned proportionally rather than stretched', () => {
  const gapped = { times: [T, T + 900, T + 3600], step: 900 }
  assert.equal(timeToLogical(T + 2250, gapped), 1.5)
  assert.equal(logicalToTime(1.5, gapped), T + 2250)
})

test('a single bar still extends both ways at the interval', () => {
  const single = { times: [T], step: 60 }
  assert.equal(timeToLogical(T + 120, single), 2)
  assert.equal(logicalToTime(-1, single), T - 60)
})

test('nothing converts without bars, a positive step or a finite input', () => {
  assert.equal(timeToLogical(T, { times: [], step: 900 }), null)
  assert.equal(logicalToTime(1, { times: [T], step: 0 }), null)
  assert.equal(timeToLogical(Number.NaN, axis), null)
})
