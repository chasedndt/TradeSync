import { test } from 'node:test'
import assert from 'node:assert/strict'
import { importTs } from './support/importTs.mjs'

const { HANDLE_RADIUS, HIT_TOLERANCE, hitLayout, hitShapes } = await importTs('src/components/canvas/drawing/hitTest.ts')

const line = {
  handles: [{ x: 100, y: 100 }, { x: 300, y: 100 }],
  segments: [[{ x: 100, y: 100 }, { x: 300, y: 100 }]],
}
const BODY = { kind: 'body' }

test('a stroke is hit within six pixels either side and missed beyond', () => {
  assert.equal(HIT_TOLERANCE, 6)
  assert.deepEqual(hitLayout(line, { x: 200, y: 106 }), BODY)
  assert.equal(hitLayout(line, { x: 200, y: 107 }), null)
})

test('an anchor handle wins over the stroke it sits on', () => {
  assert.deepEqual(hitLayout(line, { x: 301, y: 102 }), { kind: 'handle', index: 1 })
  assert.deepEqual(hitLayout(line, { x: 100 + HANDLE_RADIUS, y: 100 }), { kind: 'handle', index: 0 })
})

test('a filled rectangle is hit anywhere inside, an outline only near its edges', () => {
  const box = { left: 100, top: 100, right: 300, bottom: 200 }
  const filled = { handles: [], segments: [], area: { box, filled: true } }
  const outline = { handles: [], segments: [], area: { box, filled: false } }
  assert.deepEqual(hitLayout(filled, { x: 200, y: 150 }), BODY)
  assert.equal(hitLayout(outline, { x: 200, y: 150 }), null)
  assert.deepEqual(hitLayout(outline, { x: 200, y: 196 }), BODY)
})

test('a freehand path is hit along any of its pieces', () => {
  const layout = { handles: [], segments: [], path: [{ x: 0, y: 0 }, { x: 50, y: 50 }, { x: 100, y: 0 }] }
  assert.deepEqual(hitLayout(layout, { x: 75, y: 28 }), BODY)
  assert.equal(hitLayout(layout, { x: 50, y: 10 }), null)
})

test('text is hit inside its box', () => {
  const layout = { handles: [], segments: [], labels: [{ left: 10, top: 10, right: 90, bottom: 26 }] }
  assert.deepEqual(hitLayout(layout, { x: 50, y: 20 }), BODY)
  assert.equal(hitLayout(layout, { x: 50, y: 40 }), null)
})

test('the topmost shape wins, but the selected shape is tried first', () => {
  const lower = { id: 'lower', layout: line }
  const upper = { id: 'upper', layout: { handles: [], segments: [[{ x: 200, y: 0 }, { x: 200, y: 200 }]] } }
  const crossing = { x: 200, y: 100 }
  assert.equal(hitShapes([lower, upper], crossing, null).id, 'upper')
  assert.equal(hitShapes([lower, upper], crossing, 'lower').id, 'lower')
  assert.equal(hitShapes([lower, upper], { x: 500, y: 300 }, null), null)
})
