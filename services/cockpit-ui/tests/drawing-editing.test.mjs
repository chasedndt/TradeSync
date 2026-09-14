import { test } from 'node:test'
import assert from 'node:assert/strict'
import { importTs } from './support/importTs.mjs'

const { draggedAnchors, sameAnchors, translateAnchors } = await importTs('src/components/canvas/drawing/interaction/editing.ts')
const { strokeAnchors } = await importTs('src/components/canvas/drawing/interaction/stroke.ts')
const { linearProjection } = await importTs('src/components/canvas/drawing/projection.ts')
const { isDrawingStyle } = await importTs('src/components/canvas/drawing/shapes.ts')

const T = 1_788_800_000
const axis = { times: [T, T + 900, T + 1800, T + 2700], step: 900 }
// Ten pixels a bar from x = 100; price 80,000 at the top, one pixel per $10 below it.
const prices = { priceToCoordinate: (price) => (80000 - price) / 10, coordinateToPrice: (y) => 80000 - y * 10 }
const view = linearProjection(100, 10, prices, axis)
const style = { colour: '#e3b23c', width: 2, dashed: false }
const trendline = { id: 'a', kind: 'trendline', anchors: [{ time: T, price: 79000 }, { time: T + 900, price: 79500 }], style, label: '' }

test('the projection places an anchor past the last candle at the interval spacing', () => {
  assert.deepEqual(view.toPixel({ time: T + 4500, price: 79000 }), { x: 150, y: 100 })
  assert.deepEqual(view.toAnchor({ x: 154, y: 100 }, true), { time: T + 4500, price: 79000 })
  const unsnapped = view.toAnchor({ x: 154, y: 100 }, false)
  assert.ok(Math.abs(unsnapped.time - (T + 4860)) < 1e-6, `${unsnapped.time}`)
})

test('dragging a body moves every anchor by whole bars and the same price', () => {
  const moved = draggedAnchors(trendline, trendline.anchors, { kind: 'body' }, { x: 100, y: 100 }, { x: 124, y: 80 }, view, false)
  assert.deepEqual(moved, [{ time: T + 1800, price: 79200 }, { time: T + 2700, price: 79700 }])
})

test('a horizontal line drags in price only, and a vertical line in time only', () => {
  const horizontal = { ...trendline, kind: 'horizontal', anchors: [{ time: T, price: 79000 }] }
  assert.deepEqual(
    draggedAnchors(horizontal, horizontal.anchors, { kind: 'body' }, { x: 100, y: 100 }, { x: 160, y: 90 }, view, false),
    [{ time: T, price: 79100 }],
  )
  const vertical = { ...trendline, kind: 'vertical', anchors: [{ time: T, price: 79000 }] }
  assert.deepEqual(
    draggedAnchors(vertical, vertical.anchors, { kind: 'body' }, { x: 100, y: 100 }, { x: 120, y: 50 }, view, false),
    [{ time: T + 1800, price: 79000 }],
  )
})

test('dragging a handle moves only that anchor, onto the bar under the pointer', () => {
  const moved = draggedAnchors(trendline, trendline.anchors, { kind: 'handle', index: 1 }, { x: 110, y: 50 }, { x: 147, y: 60 }, view, false)
  assert.deepEqual(moved, [{ time: T, price: 79000 }, { time: T + 4500, price: 79400 }])
})

test('with Shift a dragged line end snaps to 45 degrees from the other end', () => {
  const moved = draggedAnchors(trendline, trendline.anchors, { kind: 'handle', index: 1 }, { x: 110, y: 50 }, { x: 150, y: 58 }, view, true)
  const start = view.toPixel(moved[0])
  const end = view.toPixel(moved[1])
  assert.ok(Math.abs((end.x - start.x) + (end.y - start.y)) < 1e-6, JSON.stringify({ start, end }))
})

test('a move that would take a price to zero or below is refused', () => {
  assert.equal(translateAnchors([{ time: T, price: 50 }], 0, -50, axis), null)
  assert.equal(sameAnchors(trendline.anchors, [...trendline.anchors]), true)
})

test('a stroke is stored simplified, in whole seconds, without repeated points', () => {
  const pixels = Array.from({ length: 30 }, (_, i) => ({ x: 100 + i * 3.1, y: 100 }))
  const anchors = pixels.map((point) => view.toAnchor(point, false))
  const stored = strokeAnchors(anchors, pixels)
  assert.equal(stored.length, 2)
  assert.ok(stored.every((anchor) => Number.isInteger(anchor.time)))
})

test('a remembered style is only trusted when the server would accept it', () => {
  assert.equal(isDrawingStyle(style), true)
  assert.equal(isDrawingStyle({ ...style, width: 5 }), false)
  assert.equal(isDrawingStyle({ ...style, colour: 'red' }), false)
  assert.equal(isDrawingStyle({ ...style, dashed: 'no' }), false)
  assert.equal(isDrawingStyle(null), false)
})
