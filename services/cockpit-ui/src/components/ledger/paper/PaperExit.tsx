import type { Observation, PaperPosition } from './paperTypes'
import { exactTime, price, words } from './paperFormat'
import styles from './PaperExit.module.css'

const seen = (o: Observation): string =>
  o.kind === 'quote'
    ? `quote at ${exactTime(o.observed_at)} (bid ${price(o.best_bid)}, ask ${price(o.best_ask)})`
    : `${o.interval_s / 60}-minute candle from ${exactTime(o.open_time)} (open ${price(o.open)}, high ${price(o.high)}, low ${price(o.low)}, close ${price(o.close)})`

const seenAt = (o: Observation): number => (o.kind === 'quote' ? o.observed_at : o.open_time)

/** Which rule closed a position, the observation that fired it and how its fill was priced; or an exit still owed. */
export function PaperExit({ position: p }: { position: PaperPosition }) {
  const owed = p.pending_exit
  if (owed) {
    return <p role="status" className="tone-warn">Exit owed: the {words(owed.rule)} fired on the {seen(owed.observation)}, but the displayed book could not fill the whole quantity ({owed.unfilled}). It fills at the next observation that can.</p>
  }
  if (p.status !== 'closed') return null
  const e = p.exit
  if (!e) return <p className={styles.exit}>Exit: {words(p.exit_reason)} at {price(p.exit_price)}. Paper ledger price, not an exchange fill.</p>
  const against = e.rule === 'time_expiry' ? ' at or after the time expiry' : e.level != null ? ` against the ${words(e.rule)} level ${price(e.level)}` : ''
  return (
    <div className={styles.exit}>
      <p>Exit: {words(e.rule)} at {price(e.fill_price)}, {exactTime(e.at)}. Paper ledger price, not an exchange fill.</p>
      <p>
        Fired by the {seen(e.trigger_observation)}{against}.
        {e.gap_fill ? ' Price was already past the level when it was seen, so the fill starts from the observed price, not the level.' : ''}
        {e.path === 'inside' ? ' The level was reached inside the candle, so the fill starts from the level.' : ''}
        {e.ambiguous_candle ? ' That candle reached both the stop and the target; the stop is taken as first.' : ''}
        {seenAt(e.fill_observation) !== seenAt(e.trigger_observation) ? ` Filled later, on the ${seen(e.fill_observation)}.` : ''}
      </p>
    </div>
  )
}
