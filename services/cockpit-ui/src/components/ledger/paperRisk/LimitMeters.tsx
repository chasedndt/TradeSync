import type { RiskState } from '../../../api/paperRiskTypes'
import { ageText, meterTone, meterWidth, percent, usd, utcStamp } from './paperRiskFormat'
import styles from './LimitMeters.module.css'

type Row = { label: string; value: string; fraction: number | null }

const short = (symbol: string) => symbol.replace('-PERP', '')

/** How much of each limit the paper account uses now, with the correlation buckets behind the bucket limit. */
export function LimitMeters({ risk }: { risk: RiskState }) {
  const u = risk.utilisation
  if (!u) return null
  const rows: Row[] = [
    { label: 'Daily loss', value: `${usd(u.daily_loss.loss_usdc)} of ${usd(u.daily_loss.limit_usdc)}`, fraction: u.daily_loss.fraction_of_limit },
    { label: 'Drawdown', value: `${percent(u.drawdown.fraction)} of ${percent(u.drawdown.limit)}`, fraction: u.drawdown.fraction_of_limit },
    { label: 'Gross exposure', value: `${percent(u.gross_exposure.fraction_of_equity)} of equity · limit ${percent(u.gross_exposure.limit)}`, fraction: u.gross_exposure.fraction_of_limit },
    ...u.symbols.map((s) => ({ label: short(s.symbol), value: `${usd(s.exposure_usdc)} · ${percent(s.fraction_of_equity)} · limit ${percent(s.limit)}`, fraction: s.fraction_of_limit })),
    ...u.buckets.filter((b) => b.exposure_usdc > 0).map((b) => ({
      label: `Bucket ${b.members.map(short).join(' + ')}`,
      value: `${usd(b.exposure_usdc)} · ${percent(b.fraction_of_equity)} · limit ${percent(b.limit)}`,
      fraction: b.fraction_of_limit,
    })),
    { label: 'Open positions', value: `${u.positions.open} of ${u.positions.limit}`, fraction: u.positions.open / u.positions.limit },
    { label: 'Oldest mark', value: `${ageText(u.marks.oldest_age_s)} · limit ${u.marks.limit_s}s`, fraction: u.marks.oldest_age_s == null ? null : u.marks.oldest_age_s / u.marks.limit_s },
  ]
  const correlation = risk.correlation
  return (
    <div className={styles.meters}>
      <h4>Limits in use</h4>
      <ul>
        {rows.map((row) => (
          <li key={row.label}>
            <div className={styles.label}>
              <span>{row.label}</span>
              <span>{row.value}</span>
            </div>
            <div className={styles.track} role="meter" aria-label={row.label} aria-valuemin={0} aria-valuemax={100}
              aria-valuenow={Math.round(Math.min(1, Math.max(0, row.fraction ?? 0)) * 100)}>
              <div className={`${styles.fill} ${styles[meterTone(row.fraction)]}`} style={{ width: meterWidth(row.fraction) }} />
            </div>
          </li>
        ))}
      </ul>
      {correlation ? (
        <p className={styles.note}>
          Correlated buckets from {correlation.window_bars} closed {correlation.bar_interval} bars at threshold {correlation.threshold ?? '—'}, measured{' '}
          {utcStamp(correlation.measured_at)} ({ageText(correlation.age_s)} ago):{' '}
          {correlation.buckets.map((bucket) => bucket.map(short).join(' + ')).join(' · ') || 'none'}.
          {correlation.unmeasured.length > 0 && ` Not measured, so entries there are refused: ${correlation.unmeasured.map(short).join(', ')}.`}
        </p>
      ) : (
        <p className="tone-warn">No correlation measurement stored yet; new entries are refused until one is.</p>
      )}
      {u.unmeasured_open_symbols.length > 0 && (
        <p className="tone-warn">Open positions without a measurement count against every bucket: {u.unmeasured_open_symbols.map(short).join(', ')}.</p>
      )}
    </div>
  )
}
