import type { EvidenceCombinationResponse } from '../../../api/evidenceCombinationTypes'
import {
  FORECAST_LABELS,
  FORECAST_ORDER,
  VERDICT_WORDS,
  comparisonFor,
  decimal,
  differenceRange,
  points,
  signedDecimal,
  verdictTone,
} from './combinationFormat'
import styles from './CombinationForecastTable.module.css'

type Forecasts = NonNullable<EvidenceCombinationResponse['forecasts']>

/**
 * The four forecasts scored on the same newest decisions. The last column is
 * each forecast's log loss minus the base rate's, decision by decision, with a
 * 95% interval at the test window's effective windows.
 */
export function CombinationForecastTable({ forecasts, comparisons }: { forecasts: Forecasts; comparisons: EvidenceCombinationResponse['comparisons'] }) {
  const versusRulebook = comparisonFor(comparisons, 'combined', 'rulebook_score', 'log_loss')

  return (
    <div className={styles.wrap}>
      <div className={styles.scroll}>
        <table className={styles.table}>
          <caption className={styles.caption}>Scored on the newest decisions · lower Brier score and log loss are better</caption>
          <thead>
            <tr>
              <th scope="col">Forecast</th>
              <th scope="col">Brier</th>
              <th scope="col">Log loss</th>
              <th scope="col">Calibration gap</th>
              <th scope="col">Log loss minus base rate</th>
            </tr>
          </thead>
          <tbody>
            {FORECAST_ORDER.map((name) => {
              const score = forecasts[name]
              const difference = name === 'base_rate' ? undefined : comparisonFor(comparisons, name, 'base_rate', 'log_loss')
              return (
                <tr key={name}>
                  <th scope="row" className={styles.name}>
                    {FORECAST_LABELS[name]}
                    {name === 'rulebook_score' && score.calibration && (
                      <span className={styles.sub}>slope {signedDecimal(score.calibration.slope, 3)} per unit of score</span>
                    )}
                  </th>
                  <td className={styles.num}>{decimal(score.brier)}</td>
                  <td className={styles.num}>{decimal(score.log_loss)}</td>
                  <td className={styles.num}>
                    {points(score.calibration_error)}
                    <span className={styles.sub}>{score.miscalibration_detectable ? 'a bin outside its interval' : 'every bin within its interval'}</span>
                  </td>
                  <td className={styles.num}>
                    {difference ? (
                      <>
                        {signedDecimal(difference.mean_difference)}
                        <span className={styles.sub}>
                          {differenceRange(difference.low, difference.high)} · <b className={verdictTone(difference.verdict)}>{VERDICT_WORDS[difference.verdict]}</b>
                        </span>
                      </>
                    ) : (
                      <span className={styles.sub}>the reference</span>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {versusRulebook && (
        <p className={styles.note}>
          Combined sources minus the rulebook score, log loss: {signedDecimal(versusRulebook.mean_difference)} ({differenceRange(versusRulebook.low, versusRulebook.high)}),{' '}
          <b className={verdictTone(versusRulebook.verdict)}>{VERDICT_WORDS[versusRulebook.verdict]}</b>.
        </p>
      )}
    </div>
  )
}
