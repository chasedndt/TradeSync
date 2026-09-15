import type { CombinationSource } from '../../../api/evidenceCombinationTypes'
import { STANDING_LABELS, conditionedRegimes, leanLabel, ratioRange, ratioText, sortSources } from './combinationFormat'
import styles from './CombinationSourceTable.module.css'

/**
 * Each source's likelihood ratios with their 95% intervals, the fitting record
 * behind them, where they were conditioned on the entry regime, and how much of
 * their face value the dependence adjustment let them keep on the test decisions.
 */
export function CombinationSourceTable({ sources, priorWindows }: { sources: CombinationSource[]; priorWindows: number }) {
  return (
    <div className={styles.wrap}>
      <h4 className={styles.title}>What each source's call is worth</h4>
      <p className={styles.lead}>
        A ratio is how much more often the source made that call before a rise than before a fall, shrunk toward ×1.00 (no update) by {priorWindows} imaginary
        windows. When ×1.00 sits inside the interval, the record cannot yet tell the source from a coin.
      </p>
      <div className={styles.scroll}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col">Source</th>
              <th scope="col">Up call</th>
              <th scope="col">Down call</th>
              <th scope="col">Fitting record</th>
              <th scope="col">Regime-conditioned</th>
              <th scope="col">Counted at</th>
            </tr>
          </thead>
          <tbody>
            {sortSources(sources).map((source) => (
              <tr key={source.source_id}>
                <th scope="row" className={styles.name}>
                  {source.label}
                  <span className={styles.sub}>{STANDING_LABELS[source.standing]} · {leanLabel(source)}</span>
                </th>
                {source.fit_calls > 0 ? (
                  <>
                    <td className={styles.num}>
                      {ratioText(source.likelihood_ratio.up_call.estimate)}
                      <span className={styles.sub}>{ratioRange(source.likelihood_ratio.up_call)}</span>
                    </td>
                    <td className={styles.num}>
                      {ratioText(source.likelihood_ratio.down_call.estimate)}
                      <span className={styles.sub}>{ratioRange(source.likelihood_ratio.down_call)}</span>
                    </td>
                    <td className={styles.num}>
                      {source.fit_calls.toLocaleString()} calls
                      <span className={styles.sub}>{source.fit_effective_windows.toFixed(1)} effective windows</span>
                    </td>
                    <td className={styles.text}>{conditionedRegimes(source)}</td>
                    <td className={styles.num}>
                      {source.test_mean_weight == null ? '—' : `${Math.round(source.test_mean_weight * 100)}%`}
                      <span className={styles.sub}>of face value on test decisions</span>
                    </td>
                  </>
                ) : (
                  <td colSpan={5} className={styles.empty}>
                    No record in the fitting window yet, so it contributes nothing; {source.test_calls.toLocaleString()} newer calls are recorded.
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
