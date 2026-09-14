import type { IChartApi } from 'lightweight-charts'

type ChartOptions = ReturnType<IChartApi['options']>
type Saved = Pick<ChartOptions, 'handleScroll' | 'handleScale'>

/**
 * Holds the chart still under press-and-drag while a drawing tool is armed or a
 * shape is being dragged, then puts the chart's own settings back.
 *
 * Only dragging the pane and dragging the axes are turned off. Wheel zoom is
 * never touched, so the operator can still zoom while drawing.
 */
export class PanLock {
  private readonly chart: IChartApi
  private readonly reasons = new Set<string>()
  private saved: Saved | null = null

  constructor(chart: IChartApi) {
    this.chart = chart
  }

  hold(reason: string): void {
    this.reasons.add(reason)
    if (this.saved) return
    const { handleScroll, handleScale } = this.chart.options()
    this.saved = structuredClone({ handleScroll, handleScale })
    this.chart.applyOptions({
      handleScroll: { pressedMouseMove: false, horzTouchDrag: false, vertTouchDrag: false },
      handleScale: { axisPressedMouseMove: { time: false, price: false } },
    })
  }

  release(reason: string): void {
    this.reasons.delete(reason)
    if (this.reasons.size === 0) this.restore()
  }

  releaseAll(): void {
    this.reasons.clear()
    this.restore()
  }

  private restore(): void {
    const saved = this.saved
    if (!saved) return
    this.saved = null
    this.chart.applyOptions(saved)
  }
}
