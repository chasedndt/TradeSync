import type {
  IChartApiBase,
  ISeriesApi,
  ISeriesPrimitive,
  ISeriesPrimitivePaneRenderer,
  ISeriesPrimitivePaneView,
  SeriesAttachedParameter,
  SeriesType,
  Time,
} from 'lightweight-charts'
import { cssColour, type Rgba } from './palette'

type PaneTarget = Parameters<ISeriesPrimitivePaneRenderer['draw']>[0]

export interface HeatCell {
  t: number // index into times
  p: number // index into priceEdges
  intensity: number // 0..1
}

export interface HeatLayer {
  times: number[] // bucket starts, epoch seconds
  bucketSeconds: number
  priceEdges: [number, number][] // [low, high] per price index
  cells: HeatCell[]
  colour: (t: number) => Rgba
}

/**
 * A heatmap painted behind the candles, as a primitive of the candle series, so
 * every cell moves with pans, zooms and axis drags exactly as the candles do.
 * A cell spans its time bucket and its price band.
 */
export class HeatmapPrimitive implements ISeriesPrimitive<Time> {
  private chart: IChartApiBase<Time> | null = null
  private series: ISeriesApi<SeriesType, Time> | null = null
  private requestUpdate: (() => void) | null = null
  private layer: HeatLayer | null = null
  private readonly view: ISeriesPrimitivePaneView

  constructor() {
    const renderer: ISeriesPrimitivePaneRenderer = { draw: (target: PaneTarget) => this.draw(target) }
    this.view = { zOrder: () => 'bottom', renderer: () => renderer }
  }

  attached(param: SeriesAttachedParameter<Time>): void {
    this.chart = param.chart
    this.series = param.series
    this.requestUpdate = param.requestUpdate
  }

  detached(): void {
    this.chart = null
    this.series = null
    this.requestUpdate = null
  }

  setLayer(layer: HeatLayer | null): void {
    this.layer = layer
    this.requestUpdate?.()
  }

  paneViews(): readonly ISeriesPrimitivePaneView[] {
    return [this.view]
  }

  private draw(target: PaneTarget): void {
    const { layer, chart, series } = this
    if (!layer || !chart || !series || !layer.cells.length) return
    const timeScale = chart.timeScale()
    const xs: (number | null)[] = layer.times.map((t) => timeScale.timeToCoordinate(t as Time))
    const known: [number, number][] = []
    xs.forEach((x, i) => {
      if (x !== null) known.push([i, x])
    })
    const width = known.length >= 2 ? (known[known.length - 1][1] - known[0][1]) / (known[known.length - 1][0] - known[0][0]) : 8
    target.useBitmapCoordinateSpace(({ context, horizontalPixelRatio: hr, verticalPixelRatio: vr }) => {
      for (const cell of layer.cells) {
        const x0 = xs[cell.t] ?? (known.length ? known[0][1] + (cell.t - known[0][0]) * width : null)
        if (x0 === null || x0 === undefined) continue
        const next = xs[cell.t + 1]
        const x1 = next !== null && next !== undefined ? next : x0 + width
        const [low, high] = layer.priceEdges[cell.p] ?? [NaN, NaN]
        const top = series.priceToCoordinate(high)
        const bottom = series.priceToCoordinate(low)
        if (top === null || bottom === null) continue
        context.fillStyle = cssColour(layer.colour(cell.intensity))
        context.fillRect(Math.floor(x0 * hr), Math.floor(top * vr), Math.max(1, Math.ceil((x1 - x0) * hr)), Math.max(1, Math.ceil((bottom - top) * vr)))
      }
    })
  }
}
