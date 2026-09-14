import { test } from 'node:test'
import assert from 'node:assert/strict'
import { importTs } from './support/importTs.mjs'

const { clipLine, distanceToBoxEdge, distanceToSegment } = await importTs('src/components/canvas/drawing/geometry.ts')

const pane = { left: 0, top: 0, right: 800, bottom: 400 }

function near(actual, expected) {
  assert.ok(
    Math.abs(actual.x - expected.x) < 1e-9 && Math.abs(actual.y - expected.y) < 1e-9,
    `${JSON.stringify(actual)} is not ${JSON.stringify(expected)}`,
  )
}

test('distance to a segment is measured to its nearest point, ends included', () => {
  const a = { x: 0, y: 0 }
  const b = { x: 100, y: 0 }
  assert.equal(distanceToSegment({ x: 50, y: 6 }, a, b), 6)
  assert.equal(distanceToSegment({ x: 103, y: 4 }, a, b), 5)
  assert.equal(distanceToSegment({ x: 3, y: 4 }, a, a), 5)
})

test('a segment inside the pane is kept whole', () => {
  const [p, q] = clipLine({ x: 10, y: 10 }, { x: 200, y: 300 }, pane, 'segment')
  near(p, { x: 10, y: 10 })
  near(q, { x: 200, y: 300 })
})

test('a segment that leaves the pane is cut at the edge', () => {
  const [p, q] = clipLine({ x: 700, y: 200 }, { x: 900, y: 200 }, pane, 'segment')
  near(p, { x: 700, y: 200 })
  near(q, { x: 800, y: 200 })
})

test('a ray starts at its first anchor and runs through the second to the edge', () => {
  const [p, q] = clipLine({ x: 100, y: 300 }, { x: 200, y: 250 }, pane, 'ray')
  near(p, { x: 100, y: 300 })
  near(q, { x: 700, y: 0 })
})

test('an extended line runs edge to edge in both directions', () => {
  const [p, q] = clipLine({ x: 300, y: 200 }, { x: 400, y: 200 }, pane, 'line')
  near(p, { x: 0, y: 200 })
  near(q, { x: 800, y: 200 })
})

test('an upright line clips to the top and bottom', () => {
  const [p, q] = clipLine({ x: 250, y: 100 }, { x: 250, y: 150 }, pane, 'line')
  near(p, { x: 250, y: 0 })
  near(q, { x: 250, y: 400 })
})

test('a ray pointing away from the pane draws nothing, nor does a line that misses it', () => {
  assert.equal(clipLine({ x: 900, y: 200 }, { x: 1000, y: 200 }, pane, 'ray'), null)
  assert.equal(clipLine({ x: -10, y: 500 }, { x: 900, y: 450 }, pane, 'line'), null)
})

test('an anchor far off screen is clipped back to pane coordinates', () => {
  const [p, q] = clipLine({ x: -1e9, y: 200 }, { x: 400, y: 200 }, pane, 'segment')
  near(p, { x: 0, y: 200 })
  near(q, { x: 400, y: 200 })
})

test('distance to a box is measured to its nearest edge, inside or out', () => {
  const box = { left: 100, top: 100, right: 300, bottom: 200 }
  assert.equal(distanceToBoxEdge({ x: 200, y: 104 }, box), 4)
  assert.equal(distanceToBoxEdge({ x: 310, y: 150 }, box), 10)
})
