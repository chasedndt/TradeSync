import { test } from 'node:test'
import assert from 'node:assert/strict'
import { importTs } from './support/importTs.mjs'

const { FIB_LEVELS, fibLevels } = await importTs('src/components/canvas/drawing/fib.ts')
const { describeMeasurement, measure } = await importTs('src/components/canvas/drawing/measure.ts')
const { formatChartPrice, formatDuration } = await importTs('src/components/canvas/drawing/format.ts')

const T = 1_788_800_000

test('the fib tool draws the seven standard levels', () => {
  assert.deepEqual([...FIB_LEVELS], [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1])
})

test('fib level 1 sits at the start of the move and level 0 at its end', () => {
  const levels = new Map(fibLevels(78000, 80000).map(({ level, price }) => [level, price]))
  assert.equal(levels.get(1), 78000)
  assert.equal(levels.get(0), 80000)
  assert.equal(levels.get(0.5), 79000)
  assert.ok(Math.abs(levels.get(0.618) - 78764) < 1e-6)
})

test('the ruler reports price change, percentage, bars and time', () => {
  const axis = { times: [T, T + 900, T + 1800, T + 2700], step: 900 }
  const result = measure({ time: T, price: 80000 }, { time: T + 3600, price: 79200 }, axis)
  assert.deepEqual(result, { priceChange: -800, percent: -1, bars: 4, seconds: 3600 })
  assert.deepEqual(describeMeasurement(result), ['-800.00 (-1.00%)', '4 bars, 1h'])
})

test('durations read in their two largest units', () => {
  assert.equal(formatDuration(45 * 60), '45m')
  assert.equal(formatDuration(3 * 3600 + 15 * 60), '3h 15m')
  assert.equal(formatDuration(2 * 86400 + 4 * 3600 + 59), '2d 4h')
  assert.equal(formatDuration(86400), '1d')
  assert.equal(formatDuration(30), '30s')
  assert.equal(formatDuration(-5400), '-1h 30m')
})

test('prices keep a precision that suits their size', () => {
  assert.equal(formatChartPrice(79123.44), '79,123.4')
  assert.equal(formatChartPrice(151.268), '151.27')
  assert.equal(formatChartPrice(0.21434), '0.2143')
  assert.equal(formatChartPrice(0.00123456), '0.001235')
})
