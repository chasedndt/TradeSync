import { ColorType, CrosshairMode, LineStyle, type DeepPartial, type LineWidth, type TimeChartOptions } from 'lightweight-charts'

export interface Stroke {
  color: string
  width: LineWidth
  style: LineStyle
}

export const CANDLE = { up: '#3fb27f', down: '#e0574a' }
export const VOLUME = 'rgba(131, 151, 170, 0.45)'
export const GUIDE = 'rgba(227, 178, 60, 0.6)'

/** Each feature drawn in its own colour, none shared with the candles, so every line on the chart can be told apart. */
const BY_FEATURE_ROLE: Record<string, Stroke> = {
  'trend:average': { color: '#5ba9ff', width: 2, style: LineStyle.Solid },
  'momentum:momentum': { color: '#ebcb8b', width: 3, style: LineStyle.Solid },
  'volatility:band_upper': { color: '#b48ead', width: 1, style: LineStyle.Dashed },
  'volatility:band_lower': { color: '#b48ead', width: 1, style: LineStyle.Dashed },
  'range:range_high': { color: '#d08770', width: 1, style: LineStyle.Dotted },
  'range:range_low': { color: '#88c0d0', width: 1, style: LineStyle.Dotted },
  'drawdown:range_high': { color: '#f28fad', width: 2, style: LineStyle.SparseDotted },
  'rsi:oscillator': { color: '#81a1c1', width: 2, style: LineStyle.Solid },
  'participation:average': { color: '#ebcb8b', width: 2, style: LineStyle.Solid },
  'funding:funding': { color: '#d08770', width: 2, style: LineStyle.Solid },
  'premium:premium': { color: '#88c0d0', width: 2, style: LineStyle.Solid },
}

export const CONE: Record<string, Stroke> = {
  median_pct: { color: '#e5e9f0', width: 2, style: LineStyle.Solid },
  p25_pct: { color: '#a3be8c', width: 1, style: LineStyle.Dashed },
  p75_pct: { color: '#a3be8c', width: 1, style: LineStyle.Dashed },
  p10_pct: { color: 'rgba(163, 190, 140, 0.55)', width: 1, style: LineStyle.Dotted },
  p90_pct: { color: 'rgba(163, 190, 140, 0.55)', width: 1, style: LineStyle.Dotted },
}

export function strokeFor(featureKey: string, role: string): Stroke {
  return BY_FEATURE_ROLE[`${featureKey}:${role}`] ?? { color: '#8fb3d9', width: 2, style: LineStyle.Solid }
}

export function chartOptions(timeVisible: boolean, showTimeAxis: boolean): DeepPartial<TimeChartOptions> {
  return {
    autoSize: true,
    layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: '#8397aa', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace' },
    grid: { vertLines: { color: 'rgba(131, 151, 170, 0.08)' }, horzLines: { color: 'rgba(131, 151, 170, 0.08)' } },
    rightPriceScale: { borderColor: 'rgba(131, 151, 170, 0.25)', minimumWidth: 76 },
    timeScale: { borderColor: 'rgba(131, 151, 170, 0.25)', timeVisible, secondsVisible: false, visible: showTimeAxis, rightOffset: 4 },
    crosshair: { mode: CrosshairMode.Normal },
  }
}
