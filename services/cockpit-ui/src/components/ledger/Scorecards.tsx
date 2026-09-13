import { useState } from 'react'
import { useLabScorecards } from '../../api/hooks/useStrikeZone'
import type { LabResults, ScorecardRow } from '../../api/strikezoneTypes'
import { humanize, pct, since, toneOf, usd } from './format'
import { RegimeCohorts } from './RegimeCohorts'
import styles from './Scorecards.module.css'

/** Daily strategy scorecards per market and timeframe, with the lab's sample floors; a row opens its breakdowns. */
export function Scorecards() {
  const query = useLabScorecards()
  const data = query.data
  const floor = data?.ranking_policy?.minimum_independent_events_per_asset_timeframe
  const costs = data?.assumptions

  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h3>Strategy scorecards</h3>
          <p>
            {data?.methodology_version ?? 'active methodology'} · generated {since(data?.generated_at)}
            {floor ? ` · rankings withheld below ${floor} independent trades` : ''}
          </p>
        </div>
      </div>
      {query.isError && <p className={styles.message}>Scorecards unavailable from the state API.</p>}
      {data && data.scorecards.length === 0 && <p className={styles.message}>No scorecards posted yet.</p>}
      <div className={styles.scroll}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th aria-label="open" /><th>market</th><th>trades</th><th>won</th><th>net</th><th>per trade</th><th>profit factor</th>
              <th>max drawdown</th><th>Brier</th><th>last 7d</th><th>maturity</th>
            </tr>
          </thead>
          <tbody>{data?.scorecards.map((card) => <ScoreRow key={`${card.asset}-${card.timeframe}`} card={card} />)}</tbody>
        </table>
      </div>
      {costs && (
        <p className={styles.foot}>
          Costs assumed: {costs.liquidity}, fees {pct((costs.entry_fee_rate ?? 0) * 100, 3)} a side, {costs.adverse_slippage_bps_each_fill ?? '?'} bps
          adverse slippage per fill, funding from Hyperliquid's public history, ${costs.paper_notional_usdc ?? '?'} paper notional. {costs.note}
        </p>
      )}
      {data && data.regime.cohorts.length > 0 && <RegimeCohorts regime={data.regime} />}
    </section>
  )
}

function ScoreRow({ card }: { card: ScorecardRow }) {
  const [open, setOpen] = useState(false)
  const week = card.rolling_7d
  const ready = card.maturity === 'evaluation_ready'
  const cost = (v: number | null) => usd(v == null ? null : -v)
  return (
    <>
      <tr className={styles.row} onClick={() => setOpen(!open)}>
        <td className={styles.caret}>{open ? '▾' : '▸'}</td>
        <td className={styles.mono}>{card.asset} {card.timeframe}</td>
        <td className={styles.mono}>{card.resolved_trades}</td>
        <td className={styles.mono}>{pct(card.win_rate_percentage)}</td>
        <td className={`${styles.mono} ${toneOf(card.net_pnl_usdc)}`}>{usd(card.net_pnl_usdc)}</td>
        <td className={`${styles.mono} ${toneOf(card.expectancy_usdc_per_trade)}`}>{usd(card.expectancy_usdc_per_trade)}</td>
        <td className={`${styles.mono} ${card.profit_factor != null && card.profit_factor >= 1 ? 'tone-good' : 'tone-bad'}`}>{card.profit_factor?.toFixed(2) ?? '—'}</td>
        <td className={`${styles.mono} tone-bad`}>{cost(card.maximum_drawdown_usdc)}</td>
        <td className={styles.mono} title="0.25 is a coin flip at 50% confidence; lower is better calibrated">{card.brier_score?.toFixed(3) ?? '—'}</td>
        <td className={styles.mono}>{week ? <>{week.trades} · <span className={toneOf(week.net_pnl_usdc)}>{usd(week.net_pnl_usdc)}</span></> : '—'}</td>
        <td><span className={ready ? styles.ready : styles.immature} title={card.score_withheld_reason ?? ''}>{humanize(card.maturity)}</span></td>
      </tr>
      {open && (
        <tr className={styles.detail}>
          <td colSpan={11}>
            <div className={styles.breakdowns}>
              <Breakdown title="By side" results={card.direction_results} />
              <Breakdown title="By session (UTC)" results={card.session_results} />
              <Breakdown title="By regime" results={card.regime_results} />
              <div>
                <h4>Exits and costs</h4>
                <p>{Object.entries(card.exit_reason_counts).map(([k, v]) => `${v} ${k}`).join(' · ') || '—'}</p>
                <p>fees {cost(card.total_fees_usdc)} · slippage {cost(card.total_slippage_usdc)} · funding {cost(card.total_funding_cost_usdc)}</p>
                <p>average hold {card.average_holding_minutes != null ? `${Math.round(card.average_holding_minutes)}m` : '—'}</p>
              </div>
              <div>
                <h4>Independence</h4>
                <p>{card.correlation_adjusted_sample} correlation-adjusted trades; {card.minimum_sample} needed</p>
                <p>{card.independent_day_count} days of {card.minimum_independent_days} · {card.independent_regime_count} regimes of {card.minimum_independent_regimes}</p>
                {card.score_withheld_reason && <p className="tone-warn">Score withheld: {card.score_withheld_reason}.</p>}
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

function Breakdown({ title, results }: { title: string; results: Record<string, LabResults> }) {
  const entries = Object.entries(results)
  return (
    <div>
      <h4>{title}</h4>
      {entries.length === 0 ? <p className="tone-dim">—</p> : entries.map(([name, r]) => (
        <p key={name} className={styles.line}>
          <span>{humanize(name)}</span>
          <span>{r.trades} · {r.trades ? Math.round((r.wins / r.trades) * 100) : 0}% won</span>
          <span className={toneOf(r.net_pnl_usdc)}>{usd(r.net_pnl_usdc)}</span>
        </p>
      ))}
    </div>
  )
}
