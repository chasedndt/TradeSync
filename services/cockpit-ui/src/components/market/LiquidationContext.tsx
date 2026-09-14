import { useQuery } from '@tanstack/react-query'
import { apiGet } from '../../api/client'

type Context = { supported: boolean; connection: { state: string; subscribed_at?: number }; note: string; events: { id: string; event_time: number; position_side: string; bankruptcy_price: number; bankruptcy_notional_usdt: number }[] }
export function LiquidationContext({ symbol }: { symbol: string }) {
  const query = useQuery({ queryKey: ['liquidation-context', symbol], queryFn: () => apiGet<Context>(`/state/market/liquidation-context?symbol=${encodeURIComponent(symbol)}`), refetchInterval: 15000 })
  const data = query.data
  return <div className="mt-4 border-t border-gray-700 pt-4">
    <h4 className="text-sm font-medium">Bybit liquidation events · context only</h4>
    <p className="text-xs text-gray-400 mt-2">Separate venue evidence; not Hyperliquid totals.</p>
    {query.isLoading && <p role="status">Connecting to observation history…</p>}
    {query.isError && <p role="status">Feed unavailable. Any retained observations may be stale.</p>}
    {data && <>
      <p className="text-xs mt-2">{data.supported ? data.connection.state.replace(/_/g, ' ') : 'Symbol not covered — BTC, ETH and SOL only'}</p>
      {data.connection.subscribed_at && <p className="text-xs text-gray-400">Current subscription since {new Date(data.connection.subscribed_at * 1000).toLocaleString()}</p>}
      {!data.events.length && <p className="text-sm mt-3">No events recorded in the retained window. This is not a zero-liquidation claim.</p>}
      <div style={{ maxHeight: 300, overflowY: 'auto' }}>{data.events.slice(0, 30).map(e => <article key={e.id} className="text-xs mt-3 border-b border-gray-700 pb-2">
        <p>{new Date(e.event_time * 1000).toLocaleTimeString()} · {e.position_side} liquidated</p>
        <p className="text-gray-400">Bankruptcy-price notional: {e.bankruptcy_notional_usdt.toLocaleString(undefined, { maximumFractionDigits: 0 })} USDT · price {e.bankruptcy_price.toLocaleString()}</p>
      </article>)}</div>
      {data.events.length > 0 && <p className="text-xs mt-2">Showing {Math.min(30, data.events.length)} of {data.events.length} retained events.</p>}
      <details className="text-xs text-gray-400 mt-3"><summary>Source and coverage</summary><p className="mt-2">{data.note}</p></details>
    </>}
  </div>
}
