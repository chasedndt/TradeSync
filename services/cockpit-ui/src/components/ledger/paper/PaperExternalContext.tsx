import type { ExternalContext } from './paperTypes'
import { exactTime, words } from './paperFormat'
import styles from './PaperExternalContext.module.css'

const TITLES: Record<string, string> = {
  bybit_liquidations: 'Bybit liquidation receipts',
  hyperliquid_book_history: 'Hyperliquid observed book history',
}

/** The receipt and book-history context snapshots, each with its own cut-off, as captured before entry. */
export function PaperExternalContext({ context }: { context?: Record<string, ExternalContext> }) {
  if (!context) return <p>No separate context snapshots in this record. Older entries are not backfilled.</p>
  return (
    <>
      {Object.entries(context).map(([source, c]) => (
        <div key={source} className={styles.context}>
          <h5>{TITLES[source] ?? source}</h5>
          <p>Status: {words(c.status)} · cutoff: {c.cutoff == null ? 'unknown' : exactTime(c.cutoff)}</p>
          <p>Retained observations: {c.events?.length ?? c.samples?.length ?? 'unknown'} · excluded: {c.excluded ?? 'unknown'} · scoring influence: {c.scoring_influence === false ? 'none' : 'not established'}</p>
          {c.reason && <p>Unavailable reason: {c.reason}</p>}
          {c.coverage && <p>{c.coverage}</p>}
        </div>
      ))}
    </>
  )
}
