import { KIND_NAMES } from './drawing/tools'
import type { ChartShape } from './drawing/types'
import { formatPrice } from './format'

interface Props {
  shapes: readonly ChartShape[]
  /** The interval on screen; a drawing made on another says which. */
  interval: string
  selectedId: string | null
  locked: boolean
  removing: boolean
  onSelect: (drawingId: string) => void
  onRemove: (drawingId: string) => void
}

/**
 * The operator's own drawings for this symbol, from every interval, listed so
 * they can be found and removed.
 *
 * Only drawings appear here. Venue-derived lines such as resting walls are not
 * the operator's and cannot be deleted — they leave when the size does.
 */
export function AnnotationList({ shapes, interval, selectedId, locked, removing, onSelect, onRemove }: Props) {
  if (shapes.length === 0) return null

  return (
    <div style={{ marginTop: 12 }}>
      <span className="pipeline-detail-label">Your drawings</span>
      <ul style={{ listStyle: 'none', padding: 0, margin: '6px 0 0' }}>
        {shapes.map((shape) => {
          const saving = !shape.version
          const selected = shape.id === selectedId
          return (
            <li key={shape.id} style={{ display: 'flex', gap: 10, alignItems: 'center', padding: '3px 0' }}>
              <button
                type="button"
                className={selected ? 'chip chip--active' : 'chip'}
                aria-pressed={selected}
                disabled={saving}
                title="Select it on the chart"
                onClick={() => onSelect(shape.id)}
              >
                {title(shape)}
              </button>
              <span className="metric-sub">{details(shape, interval)}</span>
              <button
                type="button"
                className="chip"
                style={{ marginLeft: 'auto' }}
                disabled={removing || locked || saving}
                title={locked ? 'Unlock drawings to remove them' : undefined}
                onClick={() => onRemove(shape.id)}
              >
                Remove
              </button>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

function title(shape: ChartShape): string {
  const name = KIND_NAMES[shape.kind]
  const first = shape.anchors[0]
  if ((shape.kind === 'horizontal' || shape.kind === 'horizontal_ray') && first) {
    return `${name} ${formatPrice(first.price)}`
  }
  if ((shape.kind === 'text' || shape.kind === 'note') && shape.label) {
    return `${name}: ${shape.label.length > 40 ? `${shape.label.slice(0, 39)}…` : shape.label}`
  }
  return name
}

function details(shape: ChartShape, interval: string): string {
  if (!shape.version) return 'saving…'
  const parts: string[] = []
  if (shape.label && shape.kind !== 'text' && shape.kind !== 'note') parts.push(shape.label)
  // The version is shown because an edit supersedes rather than overwrites,
  // so "v3" means this drawing has been revised twice.
  parts.push(`v${shape.version}`)
  if (shape.interval && shape.interval !== interval) parts.push(`drawn on ${shape.interval}`)
  return parts.join(' · ')
}
