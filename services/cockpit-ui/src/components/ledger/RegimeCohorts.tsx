import type { LabRegime } from '../../api/strikezoneTypes'
import { humanize, pct, toneOf, usd } from './format'
import styles from './Scorecards.module.css'

/** Results split by session, trend or range regime, volatility and event proximity; thin cohorts are dimmed. */
export function RegimeCohorts({ regime }: { regime: LabRegime }) {
  const all = regime.aggregate
  return (
    <details className={styles.cohorts}>
      <summary>
        Regime cohorts · {regime.cohorts.length} splits
        {all ? ` · all trades ${all.resolved_trades}, ${pct(all.win_rate_percentage)} won, ${usd(all.net_pnl_usdc)}` : ''}
        {regime.minimum_independent_sample ? ` · a cohort needs ${regime.minimum_independent_sample} independent trades` : ''}
      </summary>
      <div className={styles.scroll}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>market</th><th>session</th><th>regime</th><th>volatility</th><th>events</th><th>independent</th>
              <th>trades</th><th>won</th><th>net</th><th>per trade</th>
            </tr>
          </thead>
          <tbody>
            {regime.cohorts.map((c) => (
              <tr key={`${c.asset}-${c.timeframe}-${c.utc_session}-${c.trend_range_regime}-${c.volatility_bucket}-${c.event_proximity}`}
                className={c.sample_adequacy === 'adequate' ? undefined : styles.thin}>
                <td className={styles.mono}>{c.asset ?? 'all'} {c.timeframe ?? ''}</td>
                <td>{humanize(c.utc_session)}</td>
                <td>{humanize(c.trend_range_regime)}</td>
                <td>{humanize(c.volatility_bucket)}</td>
                <td>{humanize(c.event_proximity)}</td>
                <td className={styles.mono} title={`${c.minimum_independent_sample} needed`}>
                  {c.independent_sample}{c.sample_adequacy === 'adequate' ? '' : ' · thin'}
                </td>
                <td className={styles.mono}>{c.resolved_trades}</td>
                <td className={styles.mono}>{pct(c.win_rate_percentage)}</td>
                <td className={`${styles.mono} ${toneOf(c.net_pnl_usdc)}`}>{usd(c.net_pnl_usdc)}</td>
                <td className={`${styles.mono} ${toneOf(c.expectancy_usdc_per_trade)}`}>{usd(c.expectancy_usdc_per_trade)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  )
}
