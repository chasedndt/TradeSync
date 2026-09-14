import { useEffect, useMemo, useState } from 'react'
import { useReplayChallenger, useSaveExperiment } from '../../api/hooks/useRegimeLab'
import type { RegimeLabOverview, ReplayHorizon, ReplayHours } from '../../api/regimeLabTypes'
import {
  blocker,
  checkWeights,
  draftFrom,
  experimentRequest,
  replayRequest,
  settingsKey,
  type ChallengerDraft,
  type WeightDraft,
} from './challengerForm'
import { HORIZON_LABELS, WINDOW_LABELS } from './format'
import { ReplayResult } from './ReplayResult'
import { WeightEditor } from './WeightEditor'
import styles from './ChallengerPanel.module.css'

const WINDOWS: ReplayHours[] = [24, 168, 720]
const HORIZONS: ReplayHorizon[] = [15, 60, 240]

/** Month, day, hour and minute in UTC, so a default version rarely collides with one already saved. */
function versionStamp(): string {
  const iso = new Date().toISOString()
  return `${iso.slice(5, 7)}${iso.slice(8, 10)}-${iso.slice(11, 13)}${iso.slice(14, 16)}`
}

type Scope = 'all' | 'market'

interface Fields {
  weights: WeightDraft
  hypothesis: string
  name: string
  version: string
  hours: ReplayHours
  horizon: ReplayHorizon
  scope: Scope
}

interface Props {
  symbol: string
  overview: RegimeLabOverview | undefined
  overviewError: Error | null
}

/**
 * Challenger weights with a hypothesis, judged by replaying the scorer's stored
 * decisions. Every disabled button says why beside it, and only the settings
 * last evaluated can be saved.
 */
export function ChallengerPanel({ symbol, overview, overviewError }: Props) {
  const replay = useReplayChallenger()
  const save = useSaveExperiment()
  const [fields, setFields] = useState<Fields>({
    weights: {}, hypothesis: '', name: 'Paper challenger', version: '', hours: 168, horizon: 60, scope: 'all',
  })
  const [evaluatedKey, setEvaluatedKey] = useState<string | null>(null)
  const baseline = overview?.baseline
  const blocks = useMemo(() => Object.keys(baseline?.weights ?? {}), [baseline])

  useEffect(() => {
    if (!baseline) return
    setFields((current) => (Object.keys(current.weights).length > 0 ? current : {
      ...current,
      weights: draftFrom(baseline.weights),
      version: current.version || `${baseline.version}-c${versionStamp()}`,
    }))
  }, [baseline])

  const draft: ChallengerDraft = { ...fields, symbol: fields.scope === 'market' ? symbol : null }
  const check = useMemo(() => checkWeights(fields.weights, blocks), [fields.weights, blocks])
  const current = evaluatedKey !== null && evaluatedKey === settingsKey(draft, check)
  const evaluateWhy = replay.isPending ? 'Replaying stored decisions…' : blocker('evaluate', draft, check, blocks, evaluatedKey)
  const saveWhy = save.isPending
    ? 'Saving the draft…'
    : replay.isPending ? 'Wait for the evaluation to finish before saving.' : blocker('save', draft, check, blocks, evaluatedKey)

  const set = <K extends keyof Fields>(key: K, value: Fields[K]) => setFields((previous) => ({ ...previous, [key]: value }))
  const setWeight = (block: string, raw: string) =>
    setFields((previous) => ({ ...previous, weights: { ...previous.weights, [block]: raw } }))
  const evaluate = () => {
    if (!check.weights) return
    const key = settingsKey(draft, check)
    setEvaluatedKey(null)
    save.reset()
    replay.mutate(replayRequest(draft, check.weights), { onSuccess: () => setEvaluatedKey(key) })
  }
  const saveDraft = () => {
    if (check.weights) save.mutate(experimentRequest(draft, check.weights))
  }

  return (
    <section className={`panel ${styles.panel}`} aria-labelledby="challenger-title">
      <div className="panel-heading">
        <div>
          <h3 id="challenger-title">Challenger</h3>
          <p>{baseline ? `Against baseline v${baseline.version}` : 'Waiting for the baseline'} · judged by replaying the scorer's stored decisions</p>
        </div>
      </div>
      {!overview ? (
        <p className={styles.state}>
          {overviewError ? `The challenger needs the baseline weights, which are unavailable: ${overviewError.message}` : 'Loading the baseline weights…'}
        </p>
      ) : (
        <div className={styles.body}>
          <WeightEditor
            blocks={blocks}
            baseline={overview.baseline.weights}
            evidence={overview.block_evidence}
            draft={fields.weights}
            check={check}
            onChange={setWeight}
            onReset={() => set('weights', draftFrom(overview.baseline.weights))}
          />
          <div className={styles.form}>
            <label className={styles.field}>
              <span>Hypothesis</span>
              <textarea rows={3} maxLength={800} value={fields.hypothesis} placeholder="If … then … because …" onChange={(event) => set('hypothesis', event.target.value)} />
              <small>{fields.hypothesis.trim().length} of at least 20 characters</small>
            </label>
            <div className={styles.pair}>
              <label className={styles.field}>
                <span>Draft name</span>
                <input value={fields.name} maxLength={120} onChange={(event) => set('name', event.target.value)} />
              </label>
              <label className={styles.field}>
                <span>Challenger version</span>
                <input value={fields.version} maxLength={40} onChange={(event) => set('version', event.target.value)} />
              </label>
            </div>
            <div className={styles.triple}>
              <label className={styles.field}>
                <span>Replay window</span>
                <select value={fields.hours} onChange={(event) => set('hours', Number(event.target.value) as ReplayHours)}>
                  {WINDOWS.map((hours) => <option key={hours} value={hours}>{WINDOW_LABELS[hours]}</option>)}
                </select>
              </label>
              <label className={styles.field}>
                <span>Outcome horizon</span>
                <select value={fields.horizon} onChange={(event) => set('horizon', Number(event.target.value) as ReplayHorizon)}>
                  {HORIZONS.map((minutes) => <option key={minutes} value={minutes}>{HORIZON_LABELS[minutes]}</option>)}
                </select>
              </label>
              <label className={styles.field}>
                <span>Markets</span>
                <select value={fields.scope} onChange={(event) => set('scope', event.target.value as Scope)}>
                  <option value="all">All markets</option>
                  <option value="market">{symbol} only</option>
                </select>
              </label>
            </div>
            <div className={styles.actions}>
              <div className={styles.action}>
                <button type="button" className={`${styles.button} ${styles.primary}`} disabled={evaluateWhy !== null} onClick={evaluate}>
                  {replay.isPending ? 'Replaying…' : 'Evaluate'}
                </button>
                {evaluateWhy && <span className={styles.why}>{evaluateWhy}</span>}
              </div>
              <div className={styles.action}>
                <button type="button" className={styles.button} disabled={saveWhy !== null} onClick={saveDraft}>
                  {save.isPending ? 'Saving…' : 'Save draft'}
                </button>
                {saveWhy && <span className={styles.why}>{saveWhy}</span>}
              </div>
            </div>
            {replay.error && <p role="alert" className={styles.error}>Evaluation failed: {replay.error.message}</p>}
            {save.error && <p role="alert" className={styles.error}>Saving failed: {save.error.message}</p>}
            {save.data && <p role="status" className={styles.saved}>Saved draft {save.data.experiment_id.slice(0, 8)} with the replay measured when it was saved.</p>}
          </div>
        </div>
      )}
      {replay.data && <ReplayResult result={replay.data} current={current} />}
    </section>
  )
}
