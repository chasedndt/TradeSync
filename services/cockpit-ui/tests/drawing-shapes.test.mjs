import { test } from 'node:test'
import assert from 'node:assert/strict'
import { importTs } from './support/importTs.mjs'

const { DEFAULT_STYLE, drawingInput, shapeFromDrawing } = await importTs('src/components/canvas/drawing/shapes.ts')
const { UndoHistory } = await importTs('src/components/canvas/drawing/undo.ts')

const T = 1_788_800_000

function stored(extra = {}) {
  return {
    drawing_id: 'd1',
    version: 3,
    symbol: 'BTC-PERP',
    interval: '15m',
    kind: 'trendline',
    points: [{ time_s: T, price: 79000 }, { time_s: T + 900, price: 79400 }],
    label: '',
    colour: '',
    ...extra,
  }
}

test('a stored drawing becomes a shape anchored in time and price', () => {
  const shape = shapeFromDrawing(stored({ style: { colour: '#4196ff', width: 3, dashed: false } }))
  assert.deepEqual(shape.anchors, [{ time: T, price: 79000 }, { time: T + 900, price: 79400 }])
  assert.deepEqual(shape.style, { colour: '#4196ff', width: 3, dashed: false })
  assert.equal(shape.interval, '15m')
  assert.equal(shape.version, 3)
})

test('a version from before styles keeps its dashed look and its stored colour', () => {
  assert.deepEqual(shapeFromDrawing(stored({ style: null })).style, { colour: '#e3b23c', width: 2, dashed: true })
  assert.deepEqual(shapeFromDrawing(stored({ kind: 'range', colour: '#3FB27F' })).style, { colour: '#3fb27f', width: 1, dashed: true })
})

test('saving keeps the interval a drawing was made on, whole seconds and clean prices', () => {
  const moved = { ...shapeFromDrawing(stored({ interval: '1h' })), anchors: [{ time: T + 0.6, price: 79000.123456789123 }, { time: T + 900, price: 79400 }] }
  const input = drawingInput(moved, 'BTC-PERP', '5m')
  assert.equal(input.interval, '1h')
  assert.equal(input.points[0].time_s, T + 1)
  assert.equal(input.points[0].price, 79000.12346)
})

test('a new shape is saved on the interval it was drawn on, with its style', () => {
  const draft = { id: 'draft', kind: 'ray', anchors: [{ time: T, price: 1 }, { time: T + 60, price: 2 }], style: DEFAULT_STYLE, label: '' }
  const input = drawingInput(draft, 'ETH-PERP', '5m')
  assert.equal(input.interval, '5m')
  assert.equal(input.kind, 'ray')
  assert.deepEqual(input.style, DEFAULT_STYLE)
})

test('undo returns the newest change first and keeps the last fifty', () => {
  const history = new UndoHistory()
  for (let i = 0; i < 55; i++) history.push({ type: 'create', id: `d${i}` })
  assert.equal(history.size, 50)
  assert.deepEqual(history.pop(), { type: 'create', id: 'd54' })
})

test('a drawing recreated by undo is found under its new id from older entries', () => {
  const history = new UndoHistory()
  history.alias('a', 'b')
  history.alias('b', 'c')
  assert.equal(history.resolve('a'), 'c')
  assert.equal(history.resolve('z'), 'z')
  history.alias('c', 'a')
  assert.ok(['a', 'b', 'c'].includes(history.resolve('a')))
})
