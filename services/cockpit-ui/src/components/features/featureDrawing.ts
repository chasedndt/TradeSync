import type { RegimeLabFeatureResult } from '../../api/types'

export interface FeatureDrawing {
  /** A histogram for positioning readings that flip sign; a line otherwise. */
  kind: 'line' | 'histogram'
  /** Draw a zero line when the reading's sign carries the meaning. */
  zeroLine: boolean
  /** How the chart is drawn, in one sentence. */
  how: string
}

export const featureName = (id: string) => id.replace(/^hl_/, '').split('_').join(' ')

/** How each catalog feature is drawn, from what it measures (its block) and how it is scored. */
export function drawingFor(feature: RegimeLabFeatureResult): FeatureDrawing {
  if (feature.block === 'positioning') {
    return { kind: 'histogram', zeroLine: true, how: 'Bars above zero are positive readings, below zero negative, against price on the left scale.' }
  }
  if (feature.block === 'liquidity') {
    return { kind: 'line', zeroLine: false, how: 'The line against its normal band (the centre and two spreads either side), with price on the left scale.' }
  }
  if (feature.score_mode === 'direct' || feature.score_mode === 'inverse') {
    return { kind: 'line', zeroLine: true, how: 'The line against zero and its normal band, with price on the left scale.' }
  }
  return { kind: 'line', zeroLine: false, how: 'The line over the last seven days, with price on the left scale.' }
}

/** What today's reading says, in words, and how far it is from normal. */
export function expectation(feature: RegimeLabFeatureResult): string {
  const z = feature.normalization?.z_score
  const distance = z != null ? ` It sits ${Math.abs(z).toFixed(1)} spreads ${z >= 0 ? 'above' : 'below'} its recent centre.` : ''
  if (feature.scoring_allowed && feature.score != null && (feature.score_mode === 'direct' || feature.score_mode === 'inverse')) {
    const side = Math.abs(feature.score) < 0.05 ? 'is close to neutral' : feature.score > 0 ? 'leans long' : 'leans short'
    const inverse = feature.score_mode === 'inverse' ? ' (an inverse feature: a higher value counts against the long side)' : ''
    return `Scored ${feature.score >= 0 ? '+' : ''}${feature.score.toFixed(2)}: this reading ${side} on the rulebook's 15-minute to 1-hour horizon${inverse}.${distance} Scores are paper evidence; no feature has earned skill yet.`
  }
  if (feature.status === 'ready' && feature.score_mode === 'playbook_specific') {
    return `Context for playbooks, not scored on its own.${distance}`
  }
  if (feature.reason) return `Not scored: ${feature.reason}.`
  return `Not scored (${feature.status.split('_').join(' ')}).${distance}`
}
