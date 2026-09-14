import type { IChartApi } from 'lightweight-charts'
import type { DrawingPrimitive } from '../DrawingPrimitive'
import { distance } from '../geometry'
import { snapAngle } from '../snap'
import { ANGLE_SNAPPED, PLACEMENT } from '../tools'
import type { Anchor, ChartShape, PixelPoint, ShapeKind, ToolId } from '../types'
import { draggedAnchors, sameAnchors } from './editing'
import { PanLock } from './panLock'
import { panePoint } from './pointer'
import { strokeAnchors } from './stroke'
import type {
  DragGesture,
  Gesture,
  InteractionHost,
  InteractionState,
  PlaceGesture,
  PlacingTool,
  StrokeGesture,
} from './types'

/** Pixels a press must travel to count as a drag; also the pencil's sampling step. */
const DRAG_THRESHOLD = 3
const PREVIEW_ID = 'drawing:preview'

/**
 * Pointer handling for drawing on the chart: placing shapes, freehand strokes,
 * and selecting and dragging what is already drawn.
 *
 * It listens in the capture phase on the chart's element. A press it takes over
 * is default-prevented, which stops the browser producing the mouse events the
 * chart pans with, so dragging moves a shape rather than the chart. A press on
 * empty chart with the cursor is left alone, and the chart pans as usual.
 */
export class DrawingInteraction {
  private readonly chart: IChartApi
  private readonly layer: DrawingPrimitive
  private readonly host: InteractionHost
  private readonly element: HTMLElement
  private readonly lock: PanLock
  private gesture: Gesture | null = null
  private draft: { kind: PlacingTool; first: Anchor } | null = null
  private ruler: ChartShape | null = null

  constructor(chart: IChartApi, layer: DrawingPrimitive, host: InteractionHost) {
    this.chart = chart
    this.layer = layer
    this.host = host
    this.element = chart.chartElement()
    this.lock = new PanLock(chart)
    this.element.addEventListener('pointerdown', this.onDown, true)
    this.element.addEventListener('pointermove', this.onMove, true)
    this.element.addEventListener('pointerup', this.onUp, true)
    this.element.addEventListener('pointercancel', this.onCancel, true)
  }

  /** The rail's tool changed: drop anything half placed, and hold the chart still while a tool is armed. */
  setTool(tool: ToolId, locked: boolean): void {
    this.draft = null
    if (this.gesture?.type !== 'drag') this.abandonGesture()
    this.layer.setPreview(null)
    this.layer.setPointerMode(tool === 'cursor' ? 'select' : 'place', locked)
    if (tool === 'cursor') this.lock.release('tool')
    else this.lock.hold('tool')
  }

  /** Esc: abandon whatever is in progress, and say whether there was anything. */
  cancel(): boolean {
    const busy = Boolean(this.draft || this.gesture || this.ruler)
    this.draft = null
    this.abandonGesture()
    this.layer.setPreview(null)
    this.clearRuler()
    return busy
  }

  dispose(): void {
    this.element.removeEventListener('pointerdown', this.onDown, true)
    this.element.removeEventListener('pointermove', this.onMove, true)
    this.element.removeEventListener('pointerup', this.onUp, true)
    this.element.removeEventListener('pointercancel', this.onCancel, true)
    this.gesture = null
    this.draft = null
    this.ruler = null
    try {
      this.lock.releaseAll()
    } catch {
      // The chart was removed first, and its options with it.
    }
    this.layer.setPreview(null)
    this.layer.setRuler(null)
  }

  private readonly onDown = (event: PointerEvent): void => {
    if (event.button !== 0 || this.gesture) return
    const point = panePoint(event, this.chart)
    if (!point.inside) return
    this.clearRuler()
    const state = this.host.state()
    if (state.tool === 'cursor') this.pressToSelect(event, point, state)
    else this.pressToPlace(event, point, state.tool)
  }

  private readonly onMove = (event: PointerEvent): void => {
    const gesture = this.gesture
    if (gesture ? gesture.pointerId !== event.pointerId : !this.draft) return
    const point = panePoint(event, this.chart)
    if (gesture?.type === 'drag') this.dragTo(gesture, point, event.shiftKey)
    else if (gesture?.type === 'stroke') this.extendStroke(gesture, point)
    else this.previewTo(point, event.shiftKey)
  }

  private readonly onUp = (event: PointerEvent): void => {
    const gesture = this.gesture
    if (!gesture || gesture.pointerId !== event.pointerId) return
    this.gesture = null
    if (gesture.type === 'drag') this.finishDrag(gesture)
    else if (gesture.type === 'stroke') this.finishStroke(gesture)
    else this.finishPlacement(gesture, panePoint(event, this.chart), event.shiftKey)
  }

  private readonly onCancel = (event: PointerEvent): void => {
    if (this.gesture?.pointerId === event.pointerId) this.abandonGesture()
  }

  private pressToSelect(event: PointerEvent, point: PixelPoint, state: InteractionState): void {
    const hit = state.hidden ? null : this.layer.hit(point)
    const shape = hit ? this.host.shape(hit.id) : undefined
    if (!hit || !shape) {
      if (state.selectedId) this.host.select(null)
      return
    }
    this.capture(event)
    this.host.select(hit.id)
    if (state.locked) return
    this.gesture = { type: 'drag', pointerId: event.pointerId, id: hit.id, part: hit.part, down: point, original: shape.anchors, moved: null }
    this.lock.hold('drag')
    this.layer.beginDrag()
  }

  private pressToPlace(event: PointerEvent, point: PixelPoint, tool: PlacingTool): void {
    const view = this.layer.projection()
    if (!view) return
    this.capture(event)
    if (PLACEMENT[tool] === 'stroke') {
      const anchor = view.toAnchor(point, false)
      if (anchor) this.gesture = { type: 'stroke', pointerId: event.pointerId, anchors: [anchor], pixels: [point] }
      return
    }
    let startedDraft = false
    if (PLACEMENT[tool] === 'two-click' && !this.draft) {
      const first = view.toAnchor(point, true)
      if (!first) return
      this.draft = { kind: tool, first }
      startedDraft = true
      this.previewTo(point, event.shiftKey)
    }
    this.gesture = { type: 'place', pointerId: event.pointerId, down: point, startedDraft }
  }

  private dragTo(gesture: DragGesture, point: PixelPoint, shift: boolean): void {
    if (!gesture.moved && distance(gesture.down, point) < DRAG_THRESHOLD) return
    const shape = this.host.shape(gesture.id)
    const view = this.layer.projection()
    if (!shape || !view) return
    const anchors = draggedAnchors(shape, gesture.original, gesture.part, gesture.down, point, view, shift)
    if (!anchors) return
    gesture.moved = anchors
    this.layer.moveDragged({ ...shape, anchors })
  }

  private extendStroke(gesture: StrokeGesture, point: PixelPoint): void {
    if (distance(gesture.pixels[gesture.pixels.length - 1], point) < DRAG_THRESHOLD) return
    const anchor = this.layer.projection()?.toAnchor(point, false)
    if (!anchor) return
    gesture.anchors.push(anchor)
    gesture.pixels.push(point)
    this.layer.setPreview(this.transient('pencil', gesture.anchors))
  }

  private previewTo(point: PixelPoint, shift: boolean): void {
    const draft = this.draft
    const second = this.secondAnchor(point, shift)
    if (draft && second) this.layer.setPreview(this.transient(draft.kind, [draft.first, second]))
  }

  private secondAnchor(point: PixelPoint, shift: boolean): Anchor | null {
    const view = this.layer.projection()
    const draft = this.draft
    if (!view || !draft) return null
    if (shift && ANGLE_SNAPPED.has(draft.kind)) {
      const origin = view.toPixel(draft.first)
      if (origin) return view.toAnchor(snapAngle(origin, point), false)
    }
    return view.toAnchor(point, true)
  }

  private finishDrag(gesture: DragGesture): void {
    this.lock.release('drag')
    const moved = gesture.moved
    const changed = moved !== null && !sameAnchors(moved, gesture.original)
    this.layer.endDrag(changed)
    if (moved && changed) this.host.move(gesture.id, moved)
  }

  private finishStroke(gesture: StrokeGesture): void {
    this.layer.setPreview(null)
    const anchors = strokeAnchors(gesture.anchors, gesture.pixels)
    // The pencil stays armed until Esc, as on TradingView.
    if (anchors.length >= 2) this.host.create('pencil', anchors)
  }

  private finishPlacement(gesture: PlaceGesture, point: PixelPoint, shift: boolean): void {
    const tool = this.host.state().tool
    if (tool === 'cursor') return
    if (PLACEMENT[tool] === 'two-click') {
      this.finishTwoClick(gesture, point, shift)
      return
    }
    const anchor = this.layer.projection()?.toAnchor(point, true)
    if (!anchor || !(anchor.price > 0)) return
    if (tool === 'text') {
      this.host.requestText(anchor, point)
    } else if (tool !== 'measure' && tool !== 'pencil') {
      this.host.create(tool, [anchor])
      this.host.placed()
    }
  }

  private finishTwoClick(gesture: PlaceGesture, point: PixelPoint, shift: boolean): void {
    const draft = this.draft
    if (!draft) return
    // A click that set the first anchor waits for a second click; a press that
    // was dragged places the shape where it is released.
    if (gesture.startedDraft && distance(gesture.down, point) < DRAG_THRESHOLD) return
    const second = this.secondAnchor(point, shift)
    this.draft = null
    this.layer.setPreview(null)
    const { kind, first } = draft
    // Two clicks on the same bar and price would be a shape of no size.
    if (second && (second.time !== first.time || second.price !== first.price)) {
      if (kind === 'measure') {
        this.ruler = this.transient('measure', [first, second])
        this.layer.setRuler(this.ruler)
      } else if (first.price > 0 && second.price > 0) {
        this.host.create(kind, [first, second])
      }
    }
    this.host.placed()
  }

  private capture(event: PointerEvent): void {
    event.preventDefault()
    try {
      this.element.setPointerCapture(event.pointerId)
    } catch {
      // The pointer was already released; the gesture ends with it.
    }
  }

  private transient(kind: ShapeKind, anchors: readonly Anchor[]): ChartShape {
    return { id: PREVIEW_ID, kind, anchors: [...anchors], style: this.host.state().style, label: '' }
  }

  private clearRuler(): void {
    if (!this.ruler) return
    this.ruler = null
    this.layer.setRuler(null)
  }

  private abandonGesture(): void {
    const gesture = this.gesture
    this.gesture = null
    if (gesture?.type === 'drag') {
      this.lock.release('drag')
      this.layer.endDrag(false)
    } else if (gesture?.type === 'stroke') {
      this.layer.setPreview(null)
    }
  }
}
