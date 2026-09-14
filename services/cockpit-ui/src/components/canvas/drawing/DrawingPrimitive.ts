import type {
  IChartApiBase,
  ISeriesApi,
  ISeriesPrimitive,
  ISeriesPrimitiveAxisView,
  ISeriesPrimitivePaneRenderer,
  ISeriesPrimitivePaneView,
  PrimitiveHoveredItem,
  SeriesAttachedParameter,
  SeriesType,
  Time,
} from 'lightweight-charts'
import type { TimeAxis } from './anchors'
import { hitShapes, type LaidOutShape } from './hitTest'
import { EMPTY_SCENE, paintScene, type SceneState } from './paintScene'
import { priceAxisViews } from './priceAxisViews'
import { createProjection, type Projection } from './projection'
import type { ChartShape, PixelPoint, ShapeHit } from './types'

type PaneTarget = Parameters<ISeriesPrimitivePaneRenderer['draw']>[0]

/** Whether pointer hover means selecting shapes or placing a new one. */
export type PointerMode = 'select' | 'place'

/**
 * The drawing layer, attached to the candle series as a primitive.
 *
 * The chart asks its primitives to paint on every redraw: a pan, a zoom, a
 * drag of either axis, an autoscale. Shapes are projected from their time and
 * price anchors at that moment, so they cannot drift from the candles the way
 * an overlay reprojected on range changes did. The layout from the last paint
 * is kept for hit testing, so a click is tested against what is on screen.
 */
export class DrawingPrimitive implements ISeriesPrimitive<Time> {
  private chart: IChartApiBase<Time> | null = null
  private series: ISeriesApi<SeriesType, Time> | null = null
  private requestUpdate: (() => void) | null = null
  private axis: TimeAxis = { times: [], step: 60 }
  private scene: SceneState = EMPTY_SCENE
  private laidOut: LaidOutShape[] = []
  private dragging = false
  private mode: PointerMode = 'select'
  private locked = false
  private readonly views: readonly ISeriesPrimitivePaneView[]
  private axisViews: readonly ISeriesPrimitiveAxisView[] = []

  constructor() {
    const renderer: ISeriesPrimitivePaneRenderer = { draw: (target) => this.paint(target) }
    this.views = [{ zOrder: () => 'top', renderer: () => renderer }]
  }

  attached({ chart, series, requestUpdate }: SeriesAttachedParameter<Time>): void {
    this.chart = chart
    this.series = series
    this.requestUpdate = requestUpdate
    this.rebuildAxisViews()
  }

  detached(): void {
    this.chart = null
    this.series = null
    this.requestUpdate = null
    this.laidOut = []
  }

  paneViews(): readonly ISeriesPrimitivePaneView[] {
    return this.views
  }

  priceAxisViews(): readonly ISeriesPrimitiveAxisView[] {
    return this.axisViews
  }

  hitTest(x: number, y: number): PrimitiveHoveredItem | null {
    if (this.mode === 'place') return { externalId: 'drawing:place', zOrder: 'top', cursorStyle: 'crosshair' }
    const hit = this.hit({ x, y })
    if (!hit) return null
    const cursorStyle = this.locked ? 'pointer' : hit.part.kind === 'handle' ? 'grab' : 'move'
    return { externalId: hit.id, zOrder: 'top', cursorStyle }
  }

  projection(): Projection | null {
    return this.chart && this.series ? createProjection(this.chart, this.series, this.axis) : null
  }

  hit(point: PixelPoint): ShapeHit | null {
    return this.scene.hidden ? null : hitShapes(this.laidOut, point, this.scene.selectedId)
  }

  /** The shape as drawn right now: the dragged copy while it is being moved. */
  displayed(id: string): ChartShape | undefined {
    if (this.scene.dragged?.id === id) return this.scene.dragged
    return this.scene.shapes.find((shape) => shape.id === id)
  }

  setAxis(axis: TimeAxis): void {
    this.axis = axis
    this.invalidate()
  }

  setShapes(shapes: readonly ChartShape[]): void {
    // A released drag stays drawn until the stored shapes arrive with its new
    // anchors, so the shape does not jump back while the save is in flight.
    this.update({ shapes, dragged: this.dragging ? this.scene.dragged : null })
    this.rebuildAxisViews()
  }

  setSelection(selectedId: string | null): void {
    this.update({ selectedId })
  }

  setHidden(hidden: boolean): void {
    this.update({ hidden })
    this.rebuildAxisViews()
  }

  setPreview(preview: ChartShape | null): void {
    this.update({ preview })
  }

  setRuler(ruler: ChartShape | null): void {
    this.update({ ruler })
  }

  setPointerMode(mode: PointerMode, locked: boolean): void {
    this.mode = mode
    this.locked = locked
  }

  beginDrag(): void {
    this.dragging = true
  }

  moveDragged(shape: ChartShape): void {
    this.update({ dragged: shape })
  }

  /** `keep` leaves the moved copy drawn until the saved shapes replace it. */
  endDrag(keep: boolean): void {
    this.dragging = false
    if (!keep) this.update({ dragged: null })
  }

  private update(changes: Partial<SceneState>): void {
    this.scene = { ...this.scene, ...changes }
    this.requestUpdate?.()
  }

  private invalidate(): void {
    this.requestUpdate?.()
  }

  private rebuildAxisViews(): void {
    const series = this.series
    this.axisViews = this.scene.hidden || !series
      ? []
      : priceAxisViews(this.scene.shapes, (id) => this.displayed(id), (price) => series.priceToCoordinate(price))
  }

  private paint(target: PaneTarget): void {
    target.useMediaCoordinateSpace(({ context, mediaSize }) => {
      const view = this.projection()
      if (!view) {
        this.laidOut = []
        return
      }
      const widths = new Map<string, number>()
      this.laidOut = paintScene(context, {
        view,
        pane: { left: 0, top: 0, right: mediaSize.width, bottom: mediaSize.height },
        measureText: (text, font) => {
          const key = `${font}\n${text}`
          let width = widths.get(key)
          if (width === undefined) {
            context.save()
            context.font = font
            width = context.measureText(text).width
            context.restore()
            widths.set(key, width)
          }
          return width
        },
      }, this.scene)
    })
  }
}
