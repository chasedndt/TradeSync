import type { ForwardTestResponse, LabCell } from '../../api/strikezoneTypes'
import { directionLabel, minutesAgo, price, share, toneOf, usd } from './format'
import styles from './ForwardMatrix.module.css'

/** Every asset by timeframe: the latest closed-candle call, how old it is, open trades, and the last week's results. */
export function ForwardMatrix({ data }: { data: ForwardTestResponse }) {
  const cellFor = (asset: string, timeframe: string) => data.cells.find((c) => c.asset === asset && c.timeframe === timeframe)
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h3>Forward test</h3>
          <p>latest closed-candle call per market and timeframe · stale after two missed runs · results over 7 days</p>
        </div>
      </div>
      <div className={styles.scroll}>
        <table className={styles.matrix}>
          <thead>
            <tr><th aria-label="asset" />{data.timeframes.map((tf) => <th key={tf}>{tf}</th>)}</tr>
          </thead>
          <tbody>
            {data.assets.map((asset) => (
              <tr key={asset}>
                <th scope="row">{asset}</th>
                {data.timeframes.map((tf) => <td key={tf}><Cell cell={cellFor(asset, tf)} /></td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function Cell({ cell }: { cell?: LabCell }) {
  if (!cell) return <span className="tone-dim">—</span>
  const side = cell.last_direction === 'long' ? styles.long : cell.last_direction === 'short' ? styles.short : styles.flat
  const trade = cell.last_trade
  return (
    <div className={`${styles.cell} ${cell.stale ? styles.stale : ''}`}>
      <div className={styles.top}>
        <span className={`${styles.dir} ${side}`}>{cell.last_direction ? directionLabel(cell.last_direction) : 'NO CALL'}</span>
        <span className={cell.stale ? 'tone-warn' : 'tone-dim'} title={`stale after ${cell.stale_after_minutes} minutes without a call`}>
          {cell.stale ? 'stale · ' : ''}{minutesAgo(cell.age_minutes)}
        </span>
      </div>
      {trade && (
        <div className={styles.trade}>
          last trade {directionLabel(trade.direction)} {price(trade.entry_price)} · stop {price(trade.invalidation_price)} · target {price(trade.target_price)} ·{' '}
          <span className={styles[trade.status]}>{trade.status}</span>
        </div>
      )}
      <div className={styles.stats}>
        <span>{cell.calls_24h} calls · {cell.trades_24h} trades 24h</span>
        <span>{cell.open_trades} open</span>
        <span>7d {cell.resolved_7d} resolved · {share(cell.win_rate_7d)} won · <b className={toneOf(cell.net_7d)}>{usd(cell.net_7d)}</b></span>
      </div>
    </div>
  )
}
