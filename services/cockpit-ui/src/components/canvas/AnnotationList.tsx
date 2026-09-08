import type { Shape } from './DrawingOverlay'
import type { PriceLevel } from './PriceChart'

interface Props {
  levels: PriceLevel[]
  shapes: Shape[]
  onRemove: (drawingId: string) => void
  removing: boolean
}

/**
 * The operator's own annotations, listed so they can be removed.
 *
 * Only annotations appear here. Venue-derived lines such as resting walls are
 * not the operator's and cannot be deleted — they leave when the size does.
 */
export function AnnotationList({ levels, shapes, onRemove, removing }: Props) {
  if (levels.length === 0 && shapes.length === 0) return null

  return (
    <div style={{ marginTop: 12 }}>
      <span className="pipeline-detail-label">Your annotations</span>
      <ul style={{ listStyle: 'none', padding: 0, margin: '6px 0 0' }}>
        {levels.map((level) => (
          <Row
            key={level.drawingId}
            primary={formatPrice(level.price)}
            secondary={level.label}
            onRemove={() => onRemove(level.drawingId)}
            removing={removing}
          />
        ))}
        {shapes.map((shape) => (
          <Row
            key={shape.drawingId}
            primary={shape.kind}
            secondary={shape.label}
            onRemove={() => onRemove(shape.drawingId)}
            removing={removing}
          />
        ))}
      </ul>
    </div>
  )
}

function Row({
  primary,
  secondary,
  onRemove,
  removing,
}: {
  primary: string
  secondary?: string
  onRemove: () => void
  removing: boolean
}) {
  return (
    <li style={{ display: 'flex', gap: 10, alignItems: 'center', padding: '3px 0' }}>
      <span className="metric-main" style={{ fontSize: 13 }}>
        {primary}
      </span>
      <span className="metric-sub">{secondary}</span>
      <button
        type="button"
        className="chip"
        style={{ marginLeft: 'auto' }}
        disabled={removing}
        onClick={onRemove}
      >
        Remove
      </button>
    </li>
  )
}

function formatPrice(value: number): string {
  return `$${value.toLocaleString('en-US', {
    minimumFractionDigits: value < 1000 ? 2 : 1,
    maximumFractionDigits: value < 1000 ? 2 : 1,
  })}`
}
