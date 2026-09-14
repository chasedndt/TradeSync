import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { apiGet } from '../../api/client'

type Level = { side: 'bids' | 'asks'; price: number; notional_usd: number }
type History = { symbol: string; status: string; age_seconds: number | null; note: string; samples: { time: number; levels: Level[] }[] }

export function LiquidityHistory({ symbol }: { symbol: string }) {
  const [windowSeconds, setWindowSeconds] = useState(900)
  const query = useQuery({ queryKey: ['book-history', symbol], queryFn: () => apiGet<History>(`/state/market/book-history?symbol=${encodeURIComponent(symbol)}`), refetchInterval: 15000 })
  const data = query.data
  const retained = data?.samples ?? []
  const end = retained[retained.length - 1]?.time ?? 0, start = end - windowSeconds
  const samples = retained.filter(s => s.time >= start)
  const levels = samples.flatMap(s => s.levels)
  const low = Math.min(...levels.map(l => l.price)), high = Math.max(...levels.map(l => l.price))
  const step = (high - low || 1) / 40
  const cells = samples.flatMap(s => {
    const bins = new Map<string, { side: string; bin: number; usd: number }>()
    for (const l of s.levels) {
      const bin = Math.min(39, Math.floor((l.price - low) / step)), key = `${l.side}:${bin}`
      bins.set(key, { side: l.side, bin, usd: (bins.get(key)?.usd ?? 0) + l.notional_usd })
    }
    return [...bins.values()].map(b => ({ ...b, time: s.time }))
  })
  const max = Math.max(1, ...cells.map(c => c.usd))
  return <section className="card" aria-label="Observed liquidity history">
    <h3 className="font-medium">Liquidity heatmap · Hyperliquid displayed orders</h3>
    <p className="text-xs text-gray-400 mt-2">Top 10 levels each side · green bids / red asks · brighter = more displayed USD notional. Not estimated liquidation levels.</p>
    <label className="text-xs block mt-3">Recorded window <select aria-label="Liquidity history window" className="bg-gray-900 p-2 rounded" value={windowSeconds} onChange={e => setWindowSeconds(Number(e.target.value))}><option value={900}>15 minutes</option><option value={3600}>1 hour</option></select></label>
    {query.isLoading && <p role="status">Loading recorded book snapshots…</p>}
    {query.isError && <p role="status">History unavailable. Existing observations below, if any, may be stale.</p>}
    {data && <p className="text-xs mt-2">{data.status} · {samples.length} snapshots · latest receipt {data.age_seconds == null ? 'not yet recorded' : `${Math.round(data.age_seconds)}s ago`}</p>}
    {samples.length > 0 && <>
      <div style={{ overflowX: 'auto' }}><svg viewBox="0 0 800 280" role="img" aria-label={`${symbol} observed resting bid and ask notional over ${windowSeconds / 60} minutes`} style={{ width: '100%', minWidth: 640, display: 'block', marginTop: 16 }}>
        <rect x="85" y="10" width="700" height="230" fill="#080f1d" />
        {cells.map(c => <rect key={`${c.time}:${c.side}:${c.bin}`} x={85 + (c.time - start) / windowSeconds * 688 + (c.side === 'asks' ? 15 / windowSeconds * 688 / 2 : 0)} y={10 + (39 - c.bin) * 5.75} width={15 / windowSeconds * 688 / 2} height="5.75" fill={c.side === 'bids' ? '#34d399' : '#fb7185'} opacity={0.15 + 0.85 * c.usd / max}>
          <title>{new Date(c.time * 1000).toLocaleTimeString()} · {c.side} · price bin {(low + c.bin * step).toFixed(2)}–{(low + (c.bin + 1) * step).toFixed(2)} · ${c.usd.toLocaleString(undefined, { maximumFractionDigits: 0 })}</title>
        </rect>)}
        <g fill="#a6b4c8" fontSize="13"><text x="0" y="20">${high.toLocaleString()}</text><text x="0" y="238">${low.toLocaleString()}</text><text x="85" y="265">{new Date(start * 1000).toLocaleTimeString()}</text><text x="785" y="265" textAnchor="end">{new Date(end * 1000).toLocaleTimeString()}</text></g>
      </svg></div>
      <p className="text-xs text-gray-400">Blank time columns mean no retained observation, not zero liquidity. Price bins and brightness rescale to this window; do not compare colours across symbols or refreshes.</p>
    </>}
    {data && <details className="text-xs text-gray-400 mt-3"><summary>Coverage and limitations</summary><p className="mt-2">{data.note} This display does not yet influence the thesis, ledger or opportunity score.</p></details>}
  </section>
}
