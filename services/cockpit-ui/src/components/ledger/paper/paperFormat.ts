/** Formatting for managed paper positions: exact times, ages, durations, prices, dollars and basis points. */

const finite = (v: number | null | undefined): v is number => v != null && Number.isFinite(v)

/** A price at up to seven significant figures, so 77,944.5 and 0.003695 both read in full. */
export const price = (v: number | null | undefined): string =>
  finite(v) ? v.toLocaleString(undefined, { maximumSignificantDigits: 7 }) : '—'

/** Signed USDC; small amounts keep four decimals because fees and funding are often cents. */
export const usdc = (v: number | null | undefined): string => {
  if (!finite(v)) return '—'
  const magnitude = Math.abs(v)
  const sign = v < 0 && magnitude >= 0.00005 ? '−' : ''
  return `${sign}${magnitude.toFixed(magnitude < 1 ? 4 : 2)} USDC`
}

export const bps = (v: number | null | undefined): string => (finite(v) ? `${v.toFixed(2)} bps` : '—')

/** A fraction such as a fee or funding rate as a percentage. */
export const pct = (fraction: number | null | undefined, digits = 3): string => (finite(fraction) ? `${(fraction * 100).toFixed(digits)}%` : '—')

/** The exact local time of an epoch-seconds reading, to the second, with the zone. */
export const exactTime = (seconds: number | null | undefined): string =>
  finite(seconds)
    ? new Date(seconds * 1000).toLocaleString(undefined, {
        year: 'numeric', month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', timeZoneName: 'short',
      })
    : 'unknown'

/** An elapsed span in its two largest units: 42 s, 3 min 5 s, 2 h 4 min, 6 d 1 h. */
export const age = (seconds: number | null | undefined): string => {
  if (!finite(seconds)) return '—'
  const s = Math.abs(seconds)
  if (s < 60) return `${s < 10 ? s.toFixed(1) : Math.floor(s)} s`
  if (s < 3600) return `${Math.floor(s / 60)} min ${Math.floor(s % 60)} s`
  if (s < 86400) return `${Math.floor(s / 3600)} h ${Math.floor((s % 3600) / 60)} min`
  return `${Math.floor(s / 86400)} d ${Math.floor((s % 86400) / 3600)} h`
}

/** A rule's holding time: whole days from two days, otherwise hours. */
export const duration = (seconds: number): string =>
  seconds >= 172800 && seconds % 86400 === 0 ? `${seconds / 86400} days` : `${+(seconds / 3600).toFixed(2)} h`

/** A rule or source name in words: trailing_stop → trailing stop. */
export const words = (name: string | null | undefined): string => (name ? name.split('_').join(' ') : '—')
