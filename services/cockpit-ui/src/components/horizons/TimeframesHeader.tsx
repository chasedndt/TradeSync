import { useRefreshHorizons } from '../../api/hooks/useHorizons'
import type { HorizonPage } from '../../api/horizonTypes'
import { price } from '../ledger/format'
import { clock } from './timeframeText'
import styles from './TimeframesHeader.module.css'

interface Props {
  symbols: string[]
  symbol: string
  onSymbol: (symbol: string) => void
  page?: HorizonPage
}

/** Market picker, when each measurement was taken (absolute times), and a refresh that measures now. */
export function TimeframesHeader({ symbols, symbol, onSymbol, page }: Props) {
  const refresh = useRefreshHorizons(symbol)
  const computed = page?.computed_at ?? {}
  const short = computed.short ? clock(computed.short) : page?.errors.short === 'measuring' ? 'measuring…' : '—'
  const long = computed.long ? clock(computed.long) : page?.errors.long === 'measuring' ? 'measuring…' : '—'
  return (
    <section className={`panel ${styles.header}`}>
      <div className={styles.title}>
        <h2>Timeframes</h2>
        <p>
          From one hour to six months: where trend and momentum stand, what followed the same state before, and which features
          earned weight out of sample. A record of the past, not a forecast.
        </p>
      </div>
      <div className={styles.side}>
        <div className={styles.chips} role="group" aria-label="Market">
          {symbols.map((s) => (
            <button key={s} type="button" className={s === symbol ? 'chip chip--active' : 'chip'} aria-pressed={s === symbol} onClick={() => onSymbol(s)}>
              {s.replace('-PERP', '')}
            </button>
          ))}
        </div>
        <div className={styles.status}>
          {page?.outlook.last_close != null && <span className={styles.price}>{price(page.outlook.last_close)}</span>}
          <span>short term measured <time dateTime={computed.short}>{short}</time></span>
          <span>daily measured <time dateTime={computed.long}>{long}</time></span>
          <button type="button" className="chip" onClick={() => refresh.mutate()} disabled={refresh.isPending}>
            {refresh.isPending ? 'measuring…' : 'refresh now'}
          </button>
        </div>
        {refresh.error && <span className={styles.error}>Refresh failed: {(refresh.error as Error).message}</span>}
      </div>
    </section>
  )
}
