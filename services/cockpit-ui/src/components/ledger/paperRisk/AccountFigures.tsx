import type { UseQueryResult } from '@tanstack/react-query'
import type { Account, LimitValues } from '../../../api/paperRiskTypes'
import { ageText, meterTone, percent, signedUsd, usd, utcStamp } from './paperRiskFormat'
import styles from './AccountFigures.module.css'

function Figure({ label, value, detail, tone }: { label: string; value: string; detail?: string; tone?: string }) {
  return (
    <div className={styles.figure}>
      <span>{label}</span>
      <strong className={tone ? styles[tone] : undefined}>{value}</strong>
      {detail && <p>{detail}</p>}
    </div>
  )
}

/** Equity, cash, day P&L against the daily loss limit, drawdown against its limit, realised costs, and P&L per UTC day. */
export function AccountFigures({ account, limits }: { account: UseQueryResult<Account, Error>; limits?: LimitValues }) {
  const a = account.data
  if (account.isError) return <p role="alert" className="tone-warn">Paper account unavailable: {account.error.message}</p>
  if (!a) return <p>Loading paper account…</p>
  const loss = Math.max(0, -a.day.pnl_usdc)
  const dayTone = a.day.pnl_usdc >= 0 ? 'good' : limits && loss >= limits.daily_loss_limit_usdc ? 'bad' : 'warn'
  return (
    <div className={styles.account}>
      <div className={styles.grid}>
        <Figure label="Equity" value={usd(a.equity_usdc)} detail={`Cash ${usd(a.cash_usdc)} · unrealised ${signedUsd(a.unrealised_usdc)}`} />
        <Figure label="Day P&L, UTC" value={signedUsd(a.day.pnl_usdc)} tone={dayTone}
          detail={limits ? `Daily loss limit ${usd(limits.daily_loss_limit_usdc)}` : 'Daily loss limit unavailable'} />
        <Figure label="Drawdown from peak" value={percent(a.drawdown_fraction)}
          tone={meterTone(limits ? a.drawdown_fraction / limits.max_drawdown_fraction : null)}
          detail={`${usd(a.drawdown_usdc)} below peak ${usd(a.peak_equity_usdc)}${limits ? ` · limit ${percent(limits.max_drawdown_fraction)}` : ''}`} />
        <Figure label="Realised net" value={signedUsd(a.realised.net_usdc)}
          detail={`${a.realised.closed_positions} closed · fees ${usd(a.realised.fees_usdc)} · funding ${usd(a.realised.funding_usdc)} · slippage ${usd(a.realised.slippage_usdc)}`} />
        <Figure label="Gross exposure" value={usd(a.gross_exposure_usdc)} detail={`Starting capital ${usd(a.starting_capital_usdc)}`} />
      </div>
      <p className={styles.note}>
        {a.realised.slippage_note} Reading {utcStamp(a.as_of)}; oldest open-position mark {ageText(a.oldest_mark_age_s)} old.
      </p>
      {a.starting_capital_note && <p className="tone-warn">{a.starting_capital_note}</p>}
      <div className={styles.scroll}>
        <table className={styles.days}>
          <caption>P&L per UTC day</caption>
          <thead>
            <tr><th scope="col">Day</th><th scope="col">Realised</th><th scope="col">Unrealised change</th><th scope="col">P&L</th></tr>
          </thead>
          <tbody>
            {a.daily_pnl.map((day) => (
              <tr key={day.day}>
                <td>{day.day}{day.complete ? '' : ' (so far)'}</td>
                <td>{signedUsd(day.realised_usdc)}</td>
                <td>{signedUsd(day.unrealised_change_usdc)}</td>
                <td className={day.pnl_usdc < 0 ? styles.warn : undefined}>{signedUsd(day.pnl_usdc)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className={styles.note}>{a.note}</p>
    </div>
  )
}
