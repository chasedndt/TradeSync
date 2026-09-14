import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiGet } from '../api/client'
import { WalletPairing } from './WalletPairing'
import { WalletActivity } from './WalletActivity'

interface Account {
  configured: boolean
  authority: string
  address?: string
  network?: string
  observed_at?: string
  account_value_usd?: number | null
  withdrawable_usd?: number | null
  total_margin_used_usd?: number | null
  open_positions?: { symbol: string; side: string; size: number; unrealized_pnl: number | null; entry_price: number | null; leverage: number | null; liquidation_price: number | null }[]
}

const dollars = (v: number | null | undefined) => v == null || !Number.isFinite(v) ? 'Unavailable' : v.toLocaleString('en-US', { style: 'currency', currency: 'USD' })

export function WatchOnlyWallet() {
  const [input, setInput] = useState('')
  const [address, setAddress] = useState('')
  const [message, setMessage] = useState('')
  const [refresh, setRefresh] = useState(false)
  const account = useQuery({
    queryKey: ['watch-only-wallet', address],
    queryFn: () => apiGet<Account>(`/state/execution/wallet-preview?address=${encodeURIComponent(address)}`),
    enabled: Boolean(address), retry: false, gcTime: 0,
    refetchOnWindowFocus: false,
    refetchInterval: refresh ? 30000 : false,
  })
  return <section className="panel p-5">
    <div className="panel-heading"><div><h2>Watch-only account</h2><p>Hyperliquid perpetual account visibility. No connection signature, key or trading permission.</p></div><span className="chip">READ ONLY</span></div>
    <WalletPairing onAddress={(value) => { setInput(value); setAddress(value); setMessage('') }} />
    <form onSubmit={(event) => {
      event.preventDefault()
      const value = input.trim()
      if (!/^0x[0-9a-fA-F]{40}$/.test(value)) { setMessage('Enter a public EVM address: 0x plus 40 hexadecimal characters. Not a private key or recovery phrase.'); return }
      setMessage(''); if (value === address) void account.refetch(); else setAddress(value)
    }} style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'end' }}>
      <label style={{ flex: '1 1 280px' }}>Public account address
        <input aria-label="Public account address" autoComplete="off" spellCheck={false} maxLength={42} value={input}
          onChange={(event) => setInput(event.target.value)} placeholder="0x…" className="w-full bg-slate-900 border border-slate-700 rounded p-3 mt-2" />
      </label>
      <button className="chip" type="submit" disabled={account.isFetching}>View account</button>
      <button className="chip" type="button" onClick={() => { setAddress(''); setInput(''); setMessage(''); setRefresh(false) }}>Clear account</button>
    </form>
    <p className="metric-sub mt-3">Your address is sent to Hyperliquid through TradeSync for these lookups. It is not saved as wallet configuration. This view is not proof of account ownership; spot balances and lifetime performance are not included.</p>
    {address && <label className="metric-sub block mt-3"><input type="checkbox" checked={refresh} onChange={e => setRefresh(e.target.checked)} /> Refresh account, orders and fills every 30 seconds while this page is visible</label>}
    {message && <p role="alert" className="tone-warn">{message}</p>}
    {address && account.isFetching && <p role="status">Reading account state…</p>}
    {address && account.isError && <p role="alert" className="tone-bad">Account read unavailable. No balance or permissions are inferred. Retry using View account.</p>}
    {address && !account.isFetching && !account.isError && account.data && <>
      <p style={{ overflowWrap: 'anywhere' }}>{account.data.address} · {account.data.network ?? 'Network not reported'} · read {account.data.observed_at ? new Date(account.data.observed_at).toLocaleString() : 'time unavailable'}</p>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {[['Perpetual account value', account.data.account_value_usd], ['Withdrawable', account.data.withdrawable_usd], ['Margin used', account.data.total_margin_used_usd]].map(([label, value]) => <div key={String(label)}><span className="metric-sub">{label}</span><div className="text-lg">{dollars(value as number | null | undefined)}</div></div>)}
      </div>
      <h3 className="mt-4">Reported perpetual positions</h3>
      {!account.data.open_positions?.length ? <p>No perpetual positions returned. This does not prove an empty spot wallet.</p> : <div style={{ overflowX: 'auto' }}><table className="w-full" style={{ minWidth: 720 }}><thead><tr><th>Symbol / side</th><th>Signed size</th><th>Entry</th><th>Leverage</th><th>Liquidation price</th><th>Unrealized P&amp;L</th></tr></thead><tbody>{account.data.open_positions.map((p) => <tr key={p.symbol}><td>{p.symbol} · {p.side}</td><td>{p.size}</td><td>{dollars(p.entry_price)}</td><td>{p.leverage == null ? 'Unavailable' : `${p.leverage}×`}</td><td>{dollars(p.liquidation_price)}</td><td>{dollars(p.unrealized_pnl)}</td></tr>)}</tbody></table></div>}
    </>}
    {address && <WalletActivity key={address} address={address} refresh={refresh} />}
  </section>
}
