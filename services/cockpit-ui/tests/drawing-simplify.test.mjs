import { test } from 'node:test'
import assert from 'node:assert/strict'
import { importTs } from './support/importTs.mjs'

const { rdpIndices, simplifyStroke } = await importTs('src/components/canvas/drawing/simplify.ts')

test('a straight stroke reduces to its two ends', () => {
  const points = Array.from({ length: 50 }, (_, i) => ({ x: i * 4, y: i * 2 }))
  assert.deepEqual(rdpIndices(points, 0.5), [0, 49])
})

test('wobble within the tolerance is dropped', () => {
  const points = [{ x: 0, y: 0 }, { x: 10, y: 0.4 }, { x: 20, y: -0.4 }, { x: 30, y: 0.3 }, { x: 40, y: 0 }]
  assert.deepEqual(rdpIndices(points, 1), [0, 4])
})

test('a spike further off the line than the tolerance is kept', () => {
  const points = [{ x: 0, y: 0 }, { x: 10, y: 0.4 }, { x: 20, y: 0 }, { x: 30, y: 40 }, { x: 40, y: 0 }, { x: 50, y: 0.4 }, { x: 60, y: 0 }]
  const kept = rdpIndices(points, 1)
  assert.ok(kept.includes(3), `kept ${kept}`)
  assert.equal(kept[0], 0)
  assert.equal(kept.at(-1), 6)
})

test('a long stroke is simplified to at most 400 points with its ends kept in order', () => {
  const points = Array.from({ length: 5000 }, (_, i) => ({
    x: i * 0.2,
    y: 100 * Math.sin(i / 40) + ((i * 7919) % 13) - 6,
  }))
  const kept = simplifyStroke(points, { epsilon: 0.5, maxPoints: 400 })
  assert.ok(kept.length >= 2 && kept.length <= 400, `kept ${kept.length}`)
  assert.equal(kept[0], 0)
  assert.equal(kept.at(-1), 4999)
  assert.ok(kept.every((index, i) => i === 0 || index > kept[i - 1]))
})

test('a two-point stroke comes back whole', () => {
  assert.deepEqual(simplifyStroke([{ x: 0, y: 0 }, { x: 5, y: 5 }]), [0, 1])
})
