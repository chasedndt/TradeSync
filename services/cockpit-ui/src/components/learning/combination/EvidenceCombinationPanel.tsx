import { useEvidenceCombination } from '../../../api/hooks/useEvidenceCombination'
import type { EvidenceCombinationResponse } from '../../../api/evidenceCombinationTypes'
import type { MeasuredReading } from '../../../api/outcomeEvidenceTypes'
import { CachedReadingNote } from '../../CachedReadingNote'
import { horizonLabel } from '../format'
import { CombinationForecastTable } from './CombinationForecastTable'
import { CombinationSourceTable } from './CombinationSourceTable'
import { ReliabilityChart } from './ReliabilityChart'
import { probabilityPct, windowSummary } from './combinationFormat'
import styles from './EvidenceCombinationPanel.module.css'

type Measured = EvidenceCombinationResponse & MeasuredReading

/**
 * Evidence combination at the selected horizon, as a research reading: each
 * source's call moves the odds of a rise by its measured likelihood ratio,
 * sources that repeat each other share a vote, and the combined probability is
 * scored on the newest decisions against the base rate and the rulebook's
 * calibrated score. Nothing here changes scoring, weights or gates.
 */
export function EvidenceCombinationPanel({ horizon }: { horizon: number }) {
  const { data, error, isLoading } = useEvidenceCombination(horizon)
  const label = `${horizonLabel(horizon)} horizon`

  return (
    <section className="panel" aria-labelledby="evidence-combination-title">
      <div className="panel-heading">
        <div>
          <h3 id="evidence-combination-title">Evidence combination</h3>
          <p>{label} · sources combined by their measured likelihood ratios · research reading with no scoring influence</p>
          {data?.status === 'ready' && <CachedReadingNote computedAt={data.computed_at} cache={data.cache} />}
        </div>
      </div>
      {error ? (
        <p className={`${styles.state} tone-bad`}>Evidence combination unavailable: {(error as Error).message}. Nothing is inferred.</p>
      ) : isLoading || !data ? (
        <p className={`${styles.state} tone-dim`}>Asking for the evidence combination…</p>
      ) : data.status === 'computing' ? (
        <p className={`${styles.state} tone-dim`}>{data.note}</p>
      ) : (
        <Reading data={data} label={label} />
      )}
    </section>
  )
}

function Reading({ data, label }: { data: Measured; label: string }) {
  const { forecasts, economics, split } = data
  const shortLevel = economics?.short_below != null && economics.short_below > 0 ? `, a short below ${probabilityPct(economics.short_below)}` : ''

  return (
    <>
      <p className={styles.reading}>{data.reading}</p>
      {forecasts && (
        <div className={styles.grid}>
          <CombinationForecastTable forecasts={forecasts} comparisons={data.comparisons} />
          <ReliabilityChart combined={forecasts.combined} baseRate={forecasts.base_rate} label={label} />
        </div>
      )}
      {data.sources.length > 0 && <CombinationSourceTable sources={data.sources} priorWindows={data.method.prior_windows} />}
      <p className={styles.foot}>
        Fitted on the older {windowSummary(split.fit)} and scored on the newest {windowSummary(split.test)}; {split.purged} fitting decisions whose
        window reached into the test period were set aside.
        {data.base_rate && ` Base rate ${probabilityPct(data.base_rate.rise_share)}.`}
        {economics?.long_above != null &&
          ` To cover the ${economics.cost_pct.toFixed(2)}% round trip a long needs above ${probabilityPct(economics.long_above)}${shortLevel}, with move sizes from the fitting window.`}
        {` Method ${data.method.version}, digest ${data.method.digest.slice(0, 12)}. ${data.note}`}
      </p>
    </>
  )
}
