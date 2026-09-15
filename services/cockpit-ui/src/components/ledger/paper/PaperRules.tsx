import type { PaperPosition } from './paperTypes'
import { age, duration, exactTime, price } from './paperFormat'
import styles from './PaperRules.module.css'

/** The versioned rules a position opened under (stop, target, trailing stop, time expiry) and where its trail stands. */
export function PaperRules({ position: p }: { position: PaperPosition }) {
  const r = p.rules
  if (!r) {
    return <p className={styles.note}>This position predates versioned rules. It recorded stop {price(p.stop)}, target {price(p.target)} and time expiry {exactTime(p.expiry)}.</p>
  }
  const t = p.trail
  const left = p.status === 'open' ? ` · ${age(Math.max(0, p.expiry - Date.now() / 1000))} left` : ''
  const trail = !t
    ? 'not recorded'
    : t.active
      ? `Active: best exit-side price ${price(t.best)}, stop ${price(t.stop)}, ${r.trail_atr} × ATR behind it. It only tightens.`
      : `Starts once the exit-side price reaches ${price(t.activate_price)} (${r.trail_activate_r} × the stop distance in favour), then follows ${price(t.distance)} (${r.trail_atr} × ATR) behind the best price. It only tightens.`
  return (
    <dl className={styles.rules}>
      <div><dt>Stop</dt><dd>{price(p.stop)} · {r.stop_atr} × ATR {price(p.atr)} from {r.atr_period} closed {r.atr_interval} candles, widened when needed so the target is at least {r.min_target_pct}% away</dd></div>
      <div><dt>Target</dt><dd>{price(p.target)} · {r.reward_risk} × the stop distance</dd></div>
      <div><dt>Trailing stop</dt><dd>{trail}</dd></div>
      <div><dt>Time expiry</dt><dd>{exactTime(p.expiry)} · {duration(r.max_hold_s)} after entry{left}</dd></div>
      <div><dt>Rules version</dt><dd>{r.version}</dd></div>
    </dl>
  )
}
