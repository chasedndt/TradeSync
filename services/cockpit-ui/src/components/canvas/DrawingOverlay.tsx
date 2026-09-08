import { useEffect, useState } from 'react'
import type { IChartApi, ISeriesApi } from 'lightweight-charts'

export interface Shape {
  drawingId: string
  kind: 'trendline' | 'range'
  points: { time_s: number; price: number }[]
  label: string
  colour?: string
}

interface Props {
  chart: IChartApi | null
  series: ISeriesApi<'Candlestick'> | null
  shapes: Shape[]
  /** Redraw trigger: changes whenever the chart's data or size changes. */
  revision: number
}

interface Placed {
  drawingId: string
  kind: 'trendline' | 'range'
  x1: number
  y1: number
  x2: number
  y2: number
  label: string
  colour: string
}

/**
 * Trendlines and ranges drawn over the chart.
 *
 * Lightweight Charts v4 has no primitive for a two-anchor shape, so these are
 * projected into an SVG overlay using the chart's own coordinate conversion.
 * That keeps one source of truth for scale: the overlay never computes its own
 * mapping, it asks the chart, so shapes stay pinned through pan and zoom.
 *
 * A shape whose anchors fall outside the visible range is not drawn. The
 * library returns null coordinates there, and guessing a position would put a
 * line somewhere the operator never placed it.
 */
export function DrawingOverlay({ chart, series, shapes, revision }: Props) {
  const [placed, setPlaced] = useState<Placed[]>([])
  const [size, setSize] = useState({ width: 0, height: 0 })

  useEffect(() => {
    if (!chart || !series) return

    function project() {
      if (!chart || !series) return
      const timeScale = chart.timeScale()
      const next: Placed[] = []

      for (const shape of shapes) {
        if (shape.points.length < 2) continue
        const [a, b] = shape.points
        const x1 = timeScale.timeToCoordinate(a.time_s as never)
        const x2 = timeScale.timeToCoordinate(b.time_s as never)
        const y1 = series.priceToCoordinate(a.price)
        const y2 = series.priceToCoordinate(b.price)
        // Null means off-scale. Drawing it anyway would place a line where the
        // operator did not put one.
        if (x1 == null || x2 == null || y1 == null || y2 == null) continue
        next.push({
          drawingId: shape.drawingId,
          kind: shape.kind,
          x1: Number(x1),
          y1: Number(y1),
          x2: Number(x2),
          y2: Number(y2),
          label: shape.label,
          colour: shape.colour || '#e3b23c',
        })
      }
      setPlaced(next)
    }

    project()
    const timeScale = chart.timeScale()
    timeScale.subscribeVisibleLogicalRangeChange(project)
    return () => timeScale.unsubscribeVisibleLogicalRangeChange(project)
  }, [chart, series, shapes, revision])

  useEffect(() => {
    if (!chart) return
    const element = (chart as unknown as { chartElement?: () => HTMLElement }).chartElement?.()
    if (!element) return
    const observer = new ResizeObserver(() => {
      setSize({ width: element.clientWidth, height: element.clientHeight })
    })
    observer.observe(element)
    setSize({ width: element.clientWidth, height: element.clientHeight })
    return () => observer.disconnect()
  }, [chart])

  if (!placed.length || !size.width) return null

  return (
    <svg
      width={size.width}
      height={size.height}
      // Pointer events off so the chart keeps its own click, crosshair and pan.
      style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}
      aria-hidden="true"
    >
      {placed.map((shape) =>
        shape.kind === 'trendline' ? (
          <g key={shape.drawingId}>
            <line
              x1={shape.x1}
              y1={shape.y1}
              x2={shape.x2}
              y2={shape.y2}
              stroke={shape.colour}
              strokeWidth={1.5}
              strokeDasharray="4 3"
            />
            {shape.label && (
              <text
                x={shape.x2 + 6}
                y={shape.y2 - 4}
                fill={shape.colour}
                fontSize="10"
                fontFamily="ui-monospace, monospace"
              >
                {shape.label}
              </text>
            )}
          </g>
        ) : (
          <g key={shape.drawingId}>
            <rect
              x={Math.min(shape.x1, shape.x2)}
              y={Math.min(shape.y1, shape.y2)}
              width={Math.abs(shape.x2 - shape.x1)}
              height={Math.abs(shape.y2 - shape.y1)}
              fill={shape.colour}
              fillOpacity={0.08}
              stroke={shape.colour}
              strokeWidth={1}
              strokeDasharray="4 3"
            />
            {shape.label && (
              <text
                x={Math.min(shape.x1, shape.x2) + 4}
                y={Math.min(shape.y1, shape.y2) - 4}
                fill={shape.colour}
                fontSize="10"
                fontFamily="ui-monospace, monospace"
              >
                {shape.label}
              </text>
            )}
          </g>
        ),
      )}
    </svg>
  )
}
