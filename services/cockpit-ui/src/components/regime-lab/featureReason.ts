import type { EvidenceCard } from '../../api/outcomeEvidenceTypes'
import type { RegimeLabFeatureResult } from '../../api/regimeLabTypes'
import { duration } from './format'

/** Why a feature row reads as it does, in one short sentence. */
export function rowReason(feature: RegimeLabFeatureResult): string {
  switch (feature.coverage_reason) {
    case 'usable':
      if (feature.scoring_allowed) {
        return feature.normalization?.fallback ? 'Scored; tick values, so the ordinary z-score is used' : 'Scored'
      }
      return feature.score_mode === 'playbook_specific'
        ? 'Context for playbooks; never scored on its own'
        : 'The catalog does not let this feature score'
    case 'stale':
      return feature.stale_after_ms > 0
        ? `Reading ${duration(feature.age_ms)} old; stale after ${duration(feature.stale_after_ms)}`
        : 'The catalog gives this reading no freshness limit'
    case 'flat':
      return 'Every recent value identical; no dispersion to score'
    case 'collecting_history':
      return feature.reason ?? `Needs ${feature.minimum_history_points} prior readings`
    case 'display_only':
      return 'Shown for context; never normalized or scored'
    default:
      if (feature.age_ms == null) {
        return feature.availability ? `No current reading; the catalog lists it as ${feature.availability}` : 'No current reading'
      }
      return feature.reason ?? 'The normalizer refused this reading'
  }
}

export type CardsState = 'loading' | 'computing' | 'error' | 'ready'

export interface CardCells {
  verdict: string
  tone: 'good' | 'warn' | 'dim'
  entries: string
}

/** A feature's evidence-card verdict and how many entries had its reading. */
export function cardCells(card: EvidenceCard | undefined, state: CardsState): CardCells {
  if (state === 'loading') return { verdict: 'loading…', tone: 'dim', entries: '…' }
  if (state === 'computing') return { verdict: 'measuring…', tone: 'dim', entries: '…' }
  if (state === 'error') return { verdict: 'unavailable', tone: 'warn', entries: '—' }
  if (!card) return { verdict: 'no card: not a directional feature', tone: 'dim', entries: '—' }
  const total = card.entries_with_reading + card.entries_without_reading
  return {
    verdict: card.earned ? `earned · ${card.earned_by.join(', ')}` : 'not earned',
    tone: card.earned ? 'good' : 'dim',
    entries: total === 0 ? 'none yet' : `${card.entries_with_reading} of ${total}`,
  }
}
