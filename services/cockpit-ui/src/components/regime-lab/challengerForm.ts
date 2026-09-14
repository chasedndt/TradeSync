import type {
  RegimeLabBlockEvidence,
  RegimeLabExperimentRequest,
  ReplayHorizon,
  ReplayHours,
  ReplayRequest,
} from '../../api/regimeLabTypes'
import { blockLabel } from './format'

export const MAX_BLOCK_WEIGHT = 0.4
export const MIN_HYPOTHESIS_LENGTH = 20
export const MIN_NAME_LENGTH = 3

/** Weights as typed: an empty entry stays empty and is never read as zero. */
export type WeightDraft = Record<string, string>

export interface ChallengerDraft {
  weights: WeightDraft
  hypothesis: string
  name: string
  version: string
  hours: ReplayHours
  horizon: ReplayHorizon
  /** One market, or null for every market. */
  symbol: string | null
}

export interface WeightCheck {
  /** Every block's weight when all of them parse; otherwise null. */
  weights: Record<string, number> | null
  issues: Record<string, string>
  sum: number
  sumsToOne: boolean
}

export const draftFrom = (weights: Record<string, number>): WeightDraft =>
  Object.fromEntries(Object.entries(weights).map(([block, weight]) => [block, weight.toFixed(2)]))

export function parseWeight(raw: string | undefined): { value: number } | { issue: string } {
  const text = (raw ?? '').trim()
  if (text === '') return { issue: 'empty' }
  if (text.startsWith('-')) return { issue: 'negative' }
  if (!/^(\d+\.?\d*|\.\d+)$/.test(text)) return { issue: 'not a number' }
  const value = Number(text)
  if (value > MAX_BLOCK_WEIGHT + 1e-9) return { issue: `above the ${MAX_BLOCK_WEIGHT.toFixed(2)} limit` }
  return { value }
}

export function checkWeights(draft: WeightDraft, blocks: string[]): WeightCheck {
  const issues: Record<string, string> = {}
  const weights: Record<string, number> = {}
  let sum = 0
  for (const block of blocks) {
    const parsed = parseWeight(draft[block])
    if ('issue' in parsed) {
      issues[block] = parsed.issue
    } else {
      weights[block] = parsed.value
      sum += parsed.value
    }
  }
  const complete = Object.keys(issues).length === 0
  return { weights: complete ? weights : null, issues, sum, sumsToOne: complete && Math.abs(sum - 1) <= 1e-9 }
}

/** Why a block's weight cannot be changed, or null when it can. */
export function lockedReason(evidence: RegimeLabBlockEvidence | undefined, baseline: number): string | null {
  if (!evidence || evidence.admitted_feature_ids.length > 0) return null
  return `No feature in this block can score, so its weight stays at the baseline ${baseline.toFixed(2)}.`
}

/** The first reason the action cannot run yet, as a sentence, or null when it can. */
export function blocker(
  action: 'evaluate' | 'save',
  draft: ChallengerDraft,
  check: WeightCheck,
  blocks: string[],
  evaluatedKey: string | null,
): string | null {
  const invalid = blocks.find((block) => check.issues[block])
  if (invalid) return `The ${blockLabel(invalid)} weight is ${check.issues[invalid]}; fix it to ${action}.`
  if (!check.sumsToOne) return `Weights add to ${check.sum.toFixed(2)}; make them add to 1.00 to ${action}.`
  const length = draft.hypothesis.trim().length
  if (length < MIN_HYPOTHESIS_LENGTH) {
    return `Write a hypothesis of at least ${MIN_HYPOTHESIS_LENGTH} characters to ${action} (${length} so far).`
  }
  if (!draft.version.trim()) return `Give the challenger a version to ${action}.`
  if (action === 'evaluate') return null
  if (draft.name.trim().length < MIN_NAME_LENGTH) return `Name the draft (at least ${MIN_NAME_LENGTH} characters) to save.`
  if (evaluatedKey !== settingsKey(draft, check)) {
    return 'Evaluate these exact weights and settings first; saving stores their replay judgement.'
  }
  return null
}

/** What a replay's result depends on; a saved draft must match the last evaluation. Name, version and hypothesis do not. */
export const settingsKey = (draft: ChallengerDraft, check: WeightCheck): string =>
  JSON.stringify({
    weights: check.weights,
    hours: draft.hours,
    horizon: draft.horizon,
    symbol: draft.symbol,
  })

export function replayRequest(draft: ChallengerDraft, weights: Record<string, number>): ReplayRequest {
  return {
    hours: draft.hours,
    horizon_minutes: draft.horizon,
    symbol: draft.symbol,
    challenger_weights: weights,
    challenger_version: draft.version.trim(),
  }
}

export function experimentRequest(draft: ChallengerDraft, weights: Record<string, number>): RegimeLabExperimentRequest {
  return {
    name: draft.name.trim(),
    version: draft.version.trim(),
    hypothesis: draft.hypothesis.trim(),
    weights,
    hours: draft.hours,
    horizon_minutes: draft.horizon,
    symbol: draft.symbol,
  }
}
