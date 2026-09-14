import type { PixelPoint } from './types'

const HALF_ROOT_TWO = Math.SQRT1_2
// The eight directions, exact on the axes so a snapped line is truly flat or upright.
const DIRECTIONS: ReadonlyArray<readonly [number, number]> = [
  [1, 0],
  [HALF_ROOT_TWO, HALF_ROOT_TWO],
  [0, 1],
  [-HALF_ROOT_TWO, HALF_ROOT_TWO],
  [-1, 0],
  [-HALF_ROOT_TWO, -HALF_ROOT_TWO],
  [0, -1],
  [HALF_ROOT_TWO, -HALF_ROOT_TWO],
]

/**
 * Move `to` so the line from `from` runs at 0, 45 or 90 degrees on screen.
 *
 * The pointer is projected onto the nearest of the eight directions, so a
 * nearly flat drag keeps its horizontal reach and loses only its tilt.
 */
export function snapAngle(from: PixelPoint, to: PixelPoint): PixelPoint {
  const dx = to.x - from.x
  const dy = to.y - from.y
  if (dx === 0 && dy === 0) return { x: to.x, y: to.y }
  const octant = ((Math.round(Math.atan2(dy, dx) / (Math.PI / 4)) % 8) + 8) % 8
  const [ux, uy] = DIRECTIONS[octant]
  const reach = dx * ux + dy * uy
  return { x: from.x + ux * reach, y: from.y + uy * reach }
}
