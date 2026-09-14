import { useState } from 'react'
import { useReceivedLiquidations } from '../../api/hooks/useLiquidity'
import type { ReceivedWindow } from '../../api/liquidityTypes'
import { price } from '../ledger/format'
import { usdCompact, when } from './marketFormat'
import styles from './LiquidationsReceived.module.css'

const WINDOWS: ReceivedWindow[] = ['1h', '24h', '7d']

/** Liquidations received from Bybit and Binance: longs against shorts forced out, over time, and the largest single events. */
export function LiquidationsReceived({ symbol }: { symbol: string }) {
  const [window, setWindow] = useState<ReceivedWindow>('24h')
  const query = useReceivedLiquidations(symbol, window)
  const data = query.data?.window === window && query.data.symbol === symbol ? query.data : undefined
  const peak = Math.max(1, ...(data?.buckets ?? []).map(([, long, short]) => Math.max(long, short)))

  return (
    <div className={styles.wrap}>
      <div className={styles.head}>
        <h4>Liquidations</h4>
        <div className={styles.chips} role="group" aria-label="Window">
          {WINDOWS.map((w) => (
            <button key={w} type="button" className={w === window ? 'chip chip--active' : 'chip'} aria-pressed={w === window} onClick={() => setWindow(w)}>{w}</button>
          ))}
        </div>
      </div>
      {query.isError && <p className={styles.muted}>Unavailable: {(query.error as Error).message}</p>}
      {data && (
        <>
          <div className={styles.totals}>
            <span className={styles.long}>Longs {usdCompact(data.totals.long)}</span>
            <span className={styles.short}>Shorts {usdCompact(data.totals.short)}</span>
            <span className={styles.muted}>{data.events} events</span>
          </div>
          <div className={styles.bars} aria-label="Liquidations over time">
            {data.buckets.map(([t, long, short]) => (
              <div key={t} className={styles.bar} title={`${when(new Date(t * 1000).toISOString())}: longs ${usdCompact(long)}, shorts ${usdCompact(short)}`}>
                <i className={styles.shortBar} style={{ height: `${(short / peak) * 100}%` }} />
                <i className={styles.longBar} style={{ height: `${(long / peak) * 100}%` }} />
              </div>
            ))}
            {!data.buckets.length && <p className={styles.muted}>None received in this window.</p>}
          </div>
          {data.largest.length > 0 && (
            <ul className={styles.list}>
              {data.largest.slice(0, 6).map((e) => (
                <li key={`${e.source}-${e.time}-${e.price}`}>
                  <span className={e.side === 'long' ? styles.long : styles.short}>{e.side}</span> {usdCompact(e.usd)} at {price(e.price)} · {e.source} · {when(e.time)}
                </li>
              ))}
            </ul>
          )}
          <p className={styles.muted}>Recording since {when(data.recording_since)}. {data.note}</p>
        </>
      )}
    </div>
  )
}
