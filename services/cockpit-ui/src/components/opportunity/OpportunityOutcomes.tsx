import { useOpportunityAttribution } from '../../api/hooks/useLearning'
import type { Attribution, OutcomeRow } from '../../api/learningTypes'
import { AttributionChips } from '../learning/AttributionChips'
import { CLASSIFICATION_LABELS, horizonLabel, netTone, signedPct } from '../learning/format'
import styles from './OpportunityOutcomes.module.css'

/** What the market did after this opportunity at each horizon, and what its readings did for the call. */
export function OpportunityOutcomes({ opportunityId }: { opportunityId: string }) {
  const { data, isLoading, error } = useOpportunityAttribution(opportunityId)
  const byHorizon = new Map(
    (data?.attributions ?? []).map((attribution): [number, Attribution] => [attribution.horizon_minutes, attribution]),
  )
  const regime = data?.entry_regime

  return (
    <section className="card bg-gray-900/20 border-gray-800" aria-labelledby="opportunity-outcomes-title">
      <h3 id="opportunity-outcomes-title" className={styles.title}>Outcome and attribution</h3>
      {isLoading ? (
        <p className={styles.message}>Loading outcomes…</p>
      ) : error ? (
        <p className={styles.message}>Outcomes unavailable: {(error as Error).message}</p>
      ) : !data?.outcomes.length ? (
        <p className={styles.message}>No horizon has been measured yet. Each of the 15m, 1h and 4h windows is measured once it has closed.</p>
      ) : (
        <>
          <p className={styles.message}>
            Entry regime: {regime ? `${regime.regime}${regime.trailing_return_pct != null ? ` (${signedPct(regime.trailing_return_pct)} trailing)` : ''}` : 'not labelled yet'}
          </p>
          <div className={styles.scroll}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th scope="col">Horizon</th>
                  <th scope="col">Result</th>
                  <th scope="col">Net after costs</th>
                  <th scope="col">Move for the call</th>
                  <th scope="col">Best</th>
                  <th scope="col">Worst</th>
                </tr>
              </thead>
              <tbody>
                {data.outcomes.map((outcome) => (
                  <OutcomeLine key={outcome.horizon_minutes} outcome={outcome} attribution={byHorizon.get(outcome.horizon_minutes)} />
                ))}
              </tbody>
            </table>
          </div>
          {data.attributions.map((attribution) => <AttributionBlock key={attribution.horizon_minutes} attribution={attribution} />)}
        </>
      )}
    </section>
  )
}

/** The result leads the row: the classification once attributed, otherwise the measurement status and its reason. */
function resultText(outcome: OutcomeRow, attribution?: Attribution): string {
  if (attribution) return CLASSIFICATION_LABELS[attribution.classification]
  if (outcome.status === 'measured') return 'Measured, not attributed yet'
  const status = outcome.status.replace(/_/g, ' ')
  const label = status.charAt(0).toUpperCase() + status.slice(1)
  return outcome.reason ? `${label} · ${outcome.reason}` : label
}

function OutcomeLine({ outcome, attribution }: { outcome: OutcomeRow; attribution?: Attribution }) {
  const measured = outcome.status === 'measured'
  return (
    <tr>
      <th scope="row">{horizonLabel(outcome.horizon_minutes)}</th>
      <td className={styles.result}>{resultText(outcome, attribution)}</td>
      <td className={attribution ? netTone(attribution.net_return_pct) : undefined}>{attribution ? signedPct(attribution.net_return_pct, 3) : '—'}</td>
      <td className={measured ? netTone(outcome.signed_return_pct) : undefined}>{measured ? signedPct(outcome.signed_return_pct, 3) : '—'}</td>
      <td>{measured ? signedPct(outcome.max_favourable_pct, 3) : '—'}</td>
      <td>{measured && outcome.max_adverse_pct != null ? signedPct(-outcome.max_adverse_pct, 3) : '—'}</td>
    </tr>
  )
}

function AttributionBlock({ attribution }: { attribution: Attribution }) {
  return (
    <div className={styles.attribution}>
      <h4 className={styles.subtitle}>{horizonLabel(attribution.horizon_minutes)} · {CLASSIFICATION_LABELS[attribution.classification]}</h4>
      <p className={styles.reason}>{attribution.reason}</p>
      <AttributionChips readings={attribution.features} showNeutral={attribution.classification === 'no_follow_through'} limit={8} />
    </div>
  )
}
