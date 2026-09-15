import { test } from 'node:test'
import assert from 'node:assert/strict'
import { importTs } from './support/importTs.mjs'

const format = await importTs('src/components/learning/combination/combinationFormat.ts')

const source = (overrides) => ({
  source_id: 'x', label: 'x', standing: 'context_only', block: null, fit_calls: 10, fit_effective_windows: 5,
  up_call_share: 0.5, unshrunk: { up_call: 1, down_call: 1 }, polarity: 'none', interval_excludes_one: false,
  likelihood_ratio: { up_call: { estimate: 1, low: 0.5, high: 2 }, down_call: { estimate: 1, low: 0.5, high: 2 } },
  regimes: [], test_calls: 0, test_mean_weight: null, ...overrides,
})

test('score differences carry a sign and a true minus; zero at the precision shown is unsigned', () => {
  assert.equal(format.signedDecimal(0.001599), '+0.0016')
  assert.equal(format.signedDecimal(-0.004), '−0.0040')
  assert.equal(format.signedDecimal(0.00001), '0.0000')
  assert.equal(format.signedDecimal(null), '—')
  assert.equal(format.differenceRange(-0.0152, 0.0159), '−0.0152 to +0.0159')
  assert.equal(format.differenceRange(null, 0.1), 'interval not measurable yet')
})

test('probabilities, gaps and ratios read in their own units', () => {
  assert.equal(format.probabilityPct(0.707097), '70.7%')
  assert.equal(format.points(0.0134), '1.3 pts')
  assert.equal(format.ratioText(1.0761), '×1.08')
  assert.equal(format.ratioRange({ estimate: 1.08, low: 0.845, high: 1.371 }), '0.84 to 1.37')
})

test('lower loss is better: verdict words and tones agree', () => {
  assert.equal(format.verdictTone('better'), 'tone-good')
  assert.equal(format.verdictTone('worse'), 'tone-bad')
  assert.equal(format.verdictTone('not_distinguishable'), 'tone-dim')
  assert.equal(format.VERDICT_WORDS.not_distinguishable, 'not distinguishable')
})

test('the comparison asked for is found, and only that one', () => {
  const comparisons = [
    { candidate: 'combined', baseline: 'base_rate', metric: 'brier', mean_difference: 1 },
    { candidate: 'combined', baseline: 'base_rate', metric: 'log_loss', mean_difference: 2 },
    { candidate: 'combined', baseline: 'rulebook_score', metric: 'log_loss', mean_difference: 3 },
  ]
  assert.equal(format.comparisonFor(comparisons, 'combined', 'base_rate', 'log_loss').mean_difference, 2)
  assert.equal(format.comparisonFor(comparisons, 'rulebook_score', 'base_rate', 'log_loss'), undefined)
})

test('sources with a fitting record come first, most effective windows first', () => {
  const ordered = format.sortSources([
    source({ source_id: 'none', label: 'a', fit_calls: 0, fit_effective_windows: 0 }),
    source({ source_id: 'thin', label: 'b', fit_effective_windows: 8 }),
    source({ source_id: 'thick', label: 'c', fit_effective_windows: 80 }),
  ])
  assert.deepEqual(ordered.map((s) => s.source_id), ['thick', 'thin', 'none'])
})

test('a lean is named only when an interval excludes one', () => {
  assert.equal(format.leanLabel({ fit_calls: 2123, interval_excludes_one: false, polarity: 'contrarian' }), 'no measurable lean')
  assert.equal(format.leanLabel({ fit_calls: 400, interval_excludes_one: true, polarity: 'contrarian' }), 'leans contrarian')
  assert.equal(format.leanLabel({ fit_calls: 400, interval_excludes_one: true, polarity: 'follows' }), 'leans with the move')
  assert.equal(format.leanLabel({ fit_calls: 0, interval_excludes_one: false, polarity: 'none' }), 'no record yet')
})

test('conditioned regimes are named, otherwise the ratio was pooled', () => {
  const regimes = [{ regime: 'falling', conditioned: true }, { regime: 'flat', conditioned: false }, { regime: 'rising', conditioned: true }]
  assert.equal(format.conditionedRegimes(source({ regimes })), 'falling, rising')
  assert.equal(format.conditionedRegimes(source({ regimes: [] })), 'none, pooled')
})

test('a window is summarised as decisions and independent evidence', () => {
  const summary = format.windowSummary({ decisions: 2219, effective_windows: 61.637, independent_windows: { per_symbol: 401, pooled: 93 } })
  assert.equal(summary, '2,219 decisions (61.6 effective windows, 93 independent)')
})

test('a reliability bin lands in the square with probability one at the top', () => {
  const frame = { left: 30, top: 8, size: 200 }
  assert.deepEqual(format.plotPoint({ mean_probability: 0.5, rise_share: 0.75, low: 0.5, high: 1 }, frame), { cx: 130, cy: 58, low: 108, high: 8 })
  assert.deepEqual(format.plotPoint({ mean_probability: 0, rise_share: 0, low: null, high: null }, frame), { cx: 30, cy: 208, low: null, high: null })
  assert.equal(format.chartSize(1200), 280)
  assert.equal(format.chartSize(60), 140)
})
