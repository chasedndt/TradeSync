import { useEffect, useMemo, useState } from 'react'
import {
  useEvaluateRegimeLab,
  useRegimeLabExperiments,
  useRegimeLabOverview,
  useSaveRegimeLab,
} from '../api/hooks'
import type { RegimeLabExperimentRequest } from '../api/types'
import { useTrackedSymbols } from '../api/hooks/useTrackedSymbols'
import { SkillGatePanel } from '../components/SkillGatePanel'

const BLOCK_LABELS: Record<string, string> = {
  price_volatility: 'Price & volatility',
  liquidity: 'Liquidity',
  positioning: 'Positioning',
  spot_premium: 'Spot premium',
  macro_flows: 'Macro flows',
}

function compact(value: number | null | undefined, digits = 4) {
  if (value == null || !Number.isFinite(value)) return '—'
  if (Math.abs(value) >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}m`
  if (Math.abs(value) >= 1_000) return `${(value / 1_000).toFixed(2)}k`
  return value.toFixed(digits)
}

function errorText(error: unknown) {
  return error instanceof Error ? error.message : 'Request failed'
}

function gateLabel(feature: {
  scoring_allowed: boolean
  status: string
  availability: string
  score_mode: string
}) {
  if (feature.scoring_allowed) return 'admitted'
  if (feature.status === 'collecting_history') return 'collecting history'
  if (feature.status === 'not_normalized') return 'display only'
  if (feature.status === 'ready' && feature.score_mode === 'playbook_specific') {
    return 'context ready'
  }
  if (feature.availability === 'planned') return 'planned'
  return feature.status.replace(/_/g, ' ')
}

export function RegimeLab() {
  const { symbols: trackedSymbols } = useTrackedSymbols()
  const [symbol, setSymbol] = useState('BTC-PERP')
  const [weights, setWeights] = useState<Record<string, number>>({})
  const [name, setName] = useState('Liquidity challenger 01')
  const [version, setVersion] = useState('1.0.0-challenger-01')
  const [hypothesis, setHypothesis] = useState('')
  const [evaluationWindow, setEvaluationWindow] = useState('current evidence snapshot')
  const [expectedEffect, setExpectedEffect] = useState('uncertain')
  const [arithmeticAnswer, setArithmeticAnswer] = useState('')
  const [reflection, setReflection] = useState('')

  const overview = useRegimeLabOverview('hyperliquid', symbol)
  const evaluate = useEvaluateRegimeLab('hyperliquid', symbol)
  const save = useSaveRegimeLab('hyperliquid', symbol)
  const history = useRegimeLabExperiments()

  useEffect(() => {
    if (overview.data && Object.keys(weights).length === 0) {
      setWeights(overview.data.baseline.weights)
    }
  }, [overview.data, weights])

  useEffect(() => {
    evaluate.reset()
    save.reset()
  // Mutations are intentionally reset only when the selected market changes.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol])

  const weightSum = useMemo(
    () => Object.values(weights).reduce((total, value) => total + value, 0),
    [weights],
  )
  const sumValid = Math.abs(weightSum - 1) < 1e-9

  const request = (): RegimeLabExperimentRequest => ({
    name,
    version,
    hypothesis,
    evaluation_window: evaluationWindow,
    expected_effect: expectedEffect,
    weights,
    arithmetic_answer: Number(arithmeticAnswer),
    reflection,
    risk_flags: [],
  })

  if (overview.isLoading) {
    return <div className="regime-lab-loading">Loading the paper laboratory…</div>
  }

  if (!overview.data || overview.error) {
    return (
      <div className="panel regime-lab-error">
        <strong>Regime Lab API unavailable</strong>
        <p>{errorText(overview.error)}</p>
      </div>
    )
  }

  const data = overview.data
  const readyFeatures = data.feature_results.filter((feature) => feature.scoring_allowed)
  const currentFeatures = data.feature_results.filter((feature) => feature.current_value != null)
  const collectingFeatures = data.feature_results.filter(
    (feature) => feature.status === 'collecting_history',
  )

  return (
    <div className="regime-lab">
      <section className="regime-hero">
        <div>
          <div className="regime-kicker">Private operator laboratory · paper shadow only</div>
          <h2>Learn the rulebook by changing it.</h2>
          <p>
            Inspect real feature evidence, form a testable hypothesis, rebalance the five
            blocks, and compare a challenger using the same market snapshot. Nothing here
            can activate a rulebook or place an order.
          </p>
        </div>
        <div className="regime-hero-controls">
          <label>
            Evidence market
            <select value={symbol} onChange={(event) => setSymbol(event.target.value)}>
              {trackedSymbols.map((item) => <option key={item}>{item}</option>)}
            </select>
          </label>
          <span className={`lab-live-pill lab-live-pill--${data.source_status.status}`}>
            <span />{data.source_status.status === 'live' ? 'Live evidence' : 'Source unavailable'}
          </span>
        </div>
      </section>

      <SkillGatePanel symbol={symbol} />

      <section className="regime-stat-grid" aria-label="Regime Lab status">
        <article className="regime-stat">
          <span>Baseline</span>
          <strong>v{data.baseline.version}</strong>
          <small>{data.baseline.status.replace('_', ' ')} · not activated</small>
        </article>
        <article className="regime-stat">
          <span>Live inputs</span>
          <strong>{currentFeatures.length}/{data.catalog.feature_count}</strong>
          <small>current values from the source contract</small>
        </article>
        <article className="regime-stat">
          <span>Scoring coverage</span>
          <strong>{(data.baseline_evaluation.data_coverage * 100).toFixed(1)}%</strong>
          <small>{readyFeatures.length} scoring features ready</small>
        </article>
        <article className="regime-stat">
          <span>Paper-risk ceiling</span>
          <strong>{data.baseline_evaluation.paper_risk_multiplier.toFixed(2)}×</strong>
          <small>minimum active cap wins</small>
        </article>
        <article className="regime-stat">
          <span>History collection</span>
          <strong>{collectingFeatures.length}</strong>
          <small>implemented features still gated</small>
        </article>
      </section>

      <div className="regime-workbench">
        <main className="regime-workbench-main">
          <section className="panel lab-section">
            <div className="lab-section-heading">
              <div><span>01</span><h3>Feature evidence</h3></div>
              <p>Source values and normalization stay on the Python side of the API.</p>
            </div>
            <div className="lab-evidence-table-wrap">
              <table className="lab-evidence-table">
                <thead><tr>
                  <th>Feature</th><th>Block</th><th>Current</th><th>History</th>
                  <th>Quality</th><th>Score</th><th>Gate</th>
                </tr></thead>
                <tbody>
                  {data.feature_results.map((feature) => (
                    <tr key={feature.feature_id}>
                      <td>
                        <strong>{feature.feature_id.replace(/^hl_/, '').replace(/_/g, ' ')}</strong>
                        <span>{feature.provenance} · {feature.unit}</span>
                      </td>
                      <td>{BLOCK_LABELS[feature.block] || feature.block}</td>
                      <td className="mono">{compact(feature.current_value)}</td>
                      <td className="mono">
                        {feature.history_count ?? 0}/{feature.minimum_history_points}
                      </td>
                      <td className="mono">{(feature.data_quality * 100).toFixed(0)}%</td>
                      <td className="mono">{compact(feature.score, 3)}</td>
                      <td>
                        <span className={`lab-gate lab-gate--${feature.scoring_allowed ? 'ready' : 'wait'}`}>
                          {gateLabel(feature)}
                        </span>
                        {!feature.scoring_allowed && feature.reason && (
                          <small className="lab-gate-reason">{feature.reason}</small>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="panel lab-section">
            <div className="lab-section-heading">
              <div><span>02</span><h3>Challenger controls</h3></div>
              <p>All five weights must sum to 1.00; no block may exceed 0.40.</p>
            </div>
            <div className="weight-editor">
              {Object.entries(weights).map(([block, weight]) => (
                <label className="weight-row" key={block}>
                  <span>{BLOCK_LABELS[block] || block}</span>
                  <input
                    type="range" min="0" max="0.4" step="0.01" value={weight}
                    onChange={(event) => setWeights({ ...weights, [block]: Number(event.target.value) })}
                  />
                  <input
                    className="weight-number" type="number" min="0" max="0.4" step="0.01"
                    value={weight}
                    onChange={(event) => setWeights({ ...weights, [block]: Number(event.target.value) })}
                  />
                </label>
              ))}
              <div className={`weight-total ${sumValid ? 'weight-total--valid' : 'weight-total--invalid'}`}>
                <span>Total weight</span><strong>{weightSum.toFixed(2)}</strong>
                <small>{sumValid ? 'valid comparator set' : 'must equal exactly 1.00'}</small>
              </div>
            </div>

            <div className="lab-form-grid">
              <label>Experiment name<input value={name} onChange={(e) => setName(e.target.value)} /></label>
              <label>Challenger version<input value={version} onChange={(e) => setVersion(e.target.value)} /></label>
              <label className="lab-form-wide">Testable hypothesis<textarea rows={3} value={hypothesis} onChange={(e) => setHypothesis(e.target.value)} placeholder="If liquidity receives more weight, then… because…" /></label>
              <label>Evaluation window<input value={evaluationWindow} onChange={(e) => setEvaluationWindow(e.target.value)} /></label>
              <label>Expected score effect<select value={expectedEffect} onChange={(e) => setExpectedEffect(e.target.value)}>
                <option value="uncertain">Uncertain</option><option value="increase">Increase</option>
                <option value="decrease">Decrease</option><option value="no_change">No change</option>
              </select></label>
            </div>
          </section>

          <section className="panel lab-section learning-gate-panel">
            <div className="lab-section-heading">
              <div><span>03</span><h3>Your learning gate</h3></div>
              <p>{data.learning.module}</p>
            </div>
            <div className="learning-grid">
              <label>
                <strong>{data.learning.arithmetic_prompt}</strong>
                <span>Enter the decimal total, not a percentage.</span>
                <input type="number" step="0.01" value={arithmeticAnswer} onChange={(e) => setArithmeticAnswer(e.target.value)} placeholder="Your answer" />
              </label>
              <label>
                <strong>{data.learning.interpretation_prompt}</strong>
                <span>Your writing is recorded for human review; it is not auto-declared correct.</span>
                <textarea rows={4} value={reflection} onChange={(e) => setReflection(e.target.value)} placeholder="Explain it in your own words…" />
              </label>
            </div>
            <div className="lab-actions">
              <button
                className="lab-button lab-button--primary"
                disabled={!sumValid || hypothesis.trim().length < 20 || evaluate.isPending}
                onClick={() => evaluate.mutate(request())}
              >{evaluate.isPending ? 'Evaluating…' : 'Evaluate challenger'}</button>
              <button
                className="lab-button"
                disabled={!evaluate.data?.persistable || save.isPending}
                onClick={() => save.mutate(request())}
              >{save.isPending ? 'Saving…' : 'Save draft experiment'}</button>
              <span>No activation endpoint exists.</span>
            </div>
            {evaluate.error && <div className="lab-callout lab-callout--bad">{errorText(evaluate.error)}</div>}
            {save.error && <div className="lab-callout lab-callout--bad">{errorText(save.error)}</div>}
            {save.data && <div className="lab-callout lab-callout--good">Draft saved · {save.data.experiment_id}</div>}
          </section>

          {evaluate.data && (
            <section className="panel lab-section lab-results">
              <div className="lab-section-heading">
                <div><span>04</span><h3>Same-evidence comparison</h3></div>
                <p>Only the rulebook weights changed.</p>
              </div>
              <div className="comparison-grid">
                <article><span>Baseline score</span><strong>{evaluate.data.comparison.baseline.weighted_score.toFixed(3)}</strong></article>
                <article><span>Challenger score</span><strong>{evaluate.data.comparison.challenger.weighted_score.toFixed(3)}</strong></article>
                <article><span>Score delta</span><strong>{evaluate.data.comparison.score_delta >= 0 ? '+' : ''}{evaluate.data.comparison.score_delta.toFixed(3)}</strong></article>
                <article><span>Learning gate</span><strong>{evaluate.data.learning_gate.complete ? 'Complete' : 'Incomplete'}</strong></article>
              </div>
              <p className="comparison-note">
                A changed score is not evidence of better performance. A fixed historical replay and guardrail results are required before any paper champion decision.
              </p>
            </section>
          )}
        </main>

        <aside className="regime-workbench-aside">
          <section className="panel lab-aside-card">
            <span className="regime-kicker">The formula</span>
            <code>Σ(weight × quality × score)<br />÷ Σ(weight × quality)</code>
            <p>Σ means “add all of these terms.” Quality reduces evidence influence; it is not predicted win probability.</p>
          </section>
          <section className="panel lab-aside-card">
            <span className="regime-kicker">Block readiness</span>
            {Object.entries(data.block_evidence).map(([block, evidence]) => (
              <div className="block-readiness" key={block}>
                <div><strong>{BLOCK_LABELS[block] || block}</strong><span>{evidence.ready_features.length}/{evidence.admitted_feature_ids.length} features</span></div>
                <div className="quality-track"><span style={{ width: `${evidence.quality * 100}%` }} /></div>
              </div>
            ))}
          </section>
          <section className="panel lab-aside-card">
            <span className="regime-kicker">Recent drafts</span>
            {history.data?.experiments.length ? history.data.experiments.map((experiment) => (
              <div className="experiment-row" key={experiment.id}>
                <strong>{experiment.name}</strong>
                <span>{experiment.baseline_version} → {experiment.challenger_version}</span>
              </div>
            )) : <p>{history.error ? 'Persistence unavailable until PostgreSQL and migrations are running.' : 'No saved experiments yet.'}</p>}
          </section>
          <section className="lab-safety-note">
            <strong>Boundary</strong>
            <p>Private learning records may be stored in PostgreSQL. Wallet secrets, approvals, and live execution controls never enter this panel.</p>
          </section>
        </aside>
      </div>
    </div>
  )
}
