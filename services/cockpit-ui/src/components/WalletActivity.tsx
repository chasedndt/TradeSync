import { useQuery } from '@tanstack/react-query'
import { apiGet } from '../api/client'

type Row = { instrument: string; side: string; price: number; size: number; time_ms: number; order_id: string; trade_id?: string; order_type?: string; reduce_only?: boolean; is_trigger?: boolean; trigger_price?: number | null; trigger_condition?: string; closed_pnl?: number | null; fee?: number | null; fee_token?: string; direction?: string }
type Dataset = { status: string; rows: Row[] | null; observed_at: string | null; received_count?: number; invalid_rows?: number; truncated?: boolean }
type Activity = { open_orders: Dataset; recent_fills: Dataset; note: string }
const number = (value: number | null | undefined) => value == null ? 'Unavailable' : value.toLocaleString(undefined, { maximumFractionDigits: 6 })

export function WalletActivity({ address, refresh }: { address: string; refresh: boolean }) {
  const query = useQuery({ queryKey: ['wallet-activity', address], queryFn: () => apiGet<Activity>(`/state/execution/wallet-activity?address=${encodeURIComponent(address)}`), gcTime: 0, retry: false, refetchOnWindowFocus: false, refetchInterval: refresh ? 30000 : false })
  return <section className="mt-5" aria-label="Read-only wallet activity">
    <button type="button" className="chip" disabled={query.isFetching} onClick={() => void query.refetch()}>Refresh orders and fills</button>
    {query.isFetching && <p role="status">Reading orders and fills…</p>}
    {query.isError && <p role="alert">Activity read failed. Earlier rows, if visible, are stale.</p>}
    {query.data && <>
      {(['open_orders', 'recent_fills'] as const).map(kind => {
        const data = query.data[kind], orders = kind === 'open_orders'
        return <section key={kind} className="mt-5">
          <h3>{orders ? 'Reported open orders' : 'Recent venue fills'}</h3>
          <p className="metric-sub">{data.status} · {data.observed_at ? new Date(data.observed_at).toLocaleString() : 'No successful read'}{data.invalid_rows ? ` · ${data.invalid_rows} malformed rows excluded` : ''}</p>
          {data.rows === null ? <p>Unavailable — not interpreted as no activity.</p> : !data.rows.length ? <p>{data.status === 'partial' ? 'No valid rows; response was incomplete.' : 'No rows returned in this endpoint’s coverage.'}</p> : <div style={{ overflowX: 'auto', maxHeight: 440 }}><table className="w-full text-sm" style={{ minWidth: 780 }}>
            <thead><tr><th>Venue time</th><th>Instrument / side</th><th>Size / price</th><th>{orders ? 'Order / trigger' : 'Closed P&L / fee'}</th><th>Order ID</th></tr></thead>
            <tbody>{data.rows.map((row, index) => <tr key={`${row.order_id}:${row.trade_id ?? index}`}>
              <td>{new Date(row.time_ms).toLocaleString()}</td><td>{row.instrument}<br />{row.side}{row.direction && <small> · {row.direction}</small>}</td>
              <td>{number(row.size)}<br />{number(row.price)}</td>
              <td>{orders ? <>{row.order_type ?? 'Type unavailable'}{row.reduce_only === true && ' · reduce only'}{row.is_trigger === true && <><br />Trigger {number(row.trigger_price)} · {row.trigger_condition}</>}</> : <>Closed P&amp;L {number(row.closed_pnl)}<br />Fee {number(row.fee)} {row.fee_token ?? '(unit unavailable)'}</>}</td>
              <td>{row.order_id}</td>
            </tr>)}</tbody>
          </table></div>}
          {data.rows && <p className="metric-sub">Showing {data.rows.length} valid rows from {data.received_count ?? 'unknown'} returned{data.truncated ? ' · display capped at 100' : ''}.</p>}
        </section>
      })}
      <details className="mt-4 metric-sub"><summary>Coverage and accounting definitions</summary><p>{query.data.note}</p></details>
    </>}
  </section>
}
