import { test } from 'node:test'
import assert from 'node:assert/strict'
import { importTs } from './support/importTs.mjs'

const { snapAngle } = await importTs('src/components/canvas/drawing/snap.ts')

const origin = { x: 100, y: 100 }

test('a nearly flat drag snaps flat and keeps its horizontal reach', () => {
  assert.deepEqual(snapAngle(origin, { x: 250, y: 108 }), { x: 250, y: 100 })
})

test('a nearly upright drag snaps upright', () => {
  assert.deepEqual(snapAngle(origin, { x: 94, y: -20 }), { x: 100, y: -20 })
})

test('a nearly diagonal drag snaps to 45 degrees in each quadrant', () => {
  for (const [dx, dy] of [[1, 1], [-1, 1], [-1, -1], [1, -1]]) {
    const snapped = snapAngle(origin, { x: 100 + dx * 80, y: 100 + dy * 70 })
    const across = snapped.x - origin.x
    const down = snapped.y - origin.y
    assert.ok(Math.abs(Math.abs(across) - Math.abs(down)) < 1e-9, JSON.stringify(snapped))
    assert.equal(Math.sign(across), dx)
    assert.equal(Math.sign(down), dy)
  }
})

test('no movement stays where it is', () => {
  assert.deepEqual(snapAngle(origin, origin), origin)
})
