import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiGet } from '../../../api/client'
import type { Fill, FundingRows, PaperPosition } from './paperTypes'
import { bps, exactTime, pct, price, usdc, words } from './paperFormat'
import styles from './PaperCosts.module.css'

const cost = (f: Fill | null | undefined): string => (f ? `${usdc(f.cost_usdc)} · ${bps(f.total_bps ?? f.cost_bps)} against the mid` : 'at close')

const measured = (label: string, f: Fill | null | undefined): string => {
  if (!f) return `${label}: not filled yet`
  const s = f.snapshot
  const book = s ? `${words(s.source)} (${words(s.precision)}) seen ${exactTime(s.observed_at)}` : 'book not recorded'
  const taken = f.levels_taken ? `${f.levels_taken.length} of ${f.levels_available} displayed levels taken` : `applied to ${price(f.reference_price)}`
  return `${label}: half spread ${bps(f.half_spread_bps)} + depth ${bps(f.depth_bps)}; ${taken}; ${book}`
}

/** Fees, slippage and settled funding for one position, each with how it was measured; stored funding rows on demand. */
export function PaperCosts({ id, position: p }: { id: string; position: PaperPosition }) {
  const [showRows, setShowRows] = useState(false)
  const rows = useQuery({ queryKey: ['paper-funding', id], queryFn: () => apiGet<FundingRows>(`/state/paper-positions/${id}/funding`), enabled: showRows })
  const { fees, slippage, funding } = p
  if (!fees || !slippage || !funding) return <p className={styles.note}>This position predates the measured breakdown of fees, slippage and funding.</p>
  return (
    <section className={styles.costs} aria-label="Fees, slippage and funding">
      <div className={styles.scroll}>
        <table>
          <thead><tr><th scope="col">Cost</th><th scope="col">Entry</th><th scope="col">Exit</th><th scope="col">How it was measured</th></tr></thead>
          <tbody>
            <tr>
              <th scope="row">Fees</th>
              <td>{usdc(fees.entry_usdc)}</td>
              <td>{usdc(fees.exit_usdc ?? fees.exit_estimate_usdc)}{fees.exit_usdc == null ? ' if closed at the last book' : ''}</td>
              <td>Hyperliquid base {fees.liquidity} fee, {pct(fees.rate)} of each fill, from the <a href={fees.schedule.source} target="_blank" rel="noreferrer">published schedule</a> read {fees.schedule.read_on}</td>
            </tr>
            <tr>
              <th scope="row">Slippage</th>
              <td>{cost(slippage.entry)}</td>
              <td>{cost(slippage.exit)}</td>
              <td>{measured('Entry', slippage.entry)}. {measured('Exit', slippage.exit)}.</td>
            </tr>
            <tr>
              <th scope="row">Funding</th>
              <td colSpan={2}>{usdc(funding.accrued_usdc)} · {funding.settled_hours} of {funding.expected_hours} settlements</td>
              <td>Hyperliquid settled hourly funding through {exactTime(funding.through)}, each hour valued at the recorded oracle price</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p>Gross {usdc(p.gross_pnl_usdc)} − fees {usdc(p.fees_usdc)} − funding {usdc(p.funding_usdc)} = net {usdc(p.net_estimate_usdc)}. Spread and depth are already inside the fill prices, so they are not subtracted again.</p>
      {funding.missing_hours.length > 0 && <p role="status" className="tone-warn">Not settled yet: {funding.missing_hours.map((hour) => exactTime(hour)).join(', ')}. The rate or the recorded price for these hours is not stored yet; no estimate stands in.</p>}
      <button className="chip" onClick={() => setShowRows(!showRows)} aria-expanded={showRows}>{showRows ? 'Hide funding rows' : 'Show funding rows'}</button>
      {showRows && rows.isLoading && <p>Loading funding rows…</p>}
      {showRows && rows.isError && <p role="alert">Funding rows unavailable: {rows.error.message}</p>}
      {showRows && rows.data && rows.data.rows.length === 0 && <p>No settlement stored for this position yet.</p>}
      {showRows && rows.data && rows.data.rows.length > 0 && (
        <div className={styles.scroll}>
          <table>
            <thead><tr><th scope="col">Settlement</th><th scope="col">Rate</th><th scope="col">Valued at</th><th scope="col">Paid</th><th scope="col">Rate received</th></tr></thead>
            <tbody>
              {rows.data.rows.map((r) => (
                <tr key={r.settled_at}>
                  <td>{exactTime(r.settled_at)}</td>
                  <td>{pct(r.funding_rate, 5)}</td>
                  <td>{price(r.price)} · {words(r.price_source.split('.').pop())} seen {exactTime(r.price_observed_at)}</td>
                  <td>{usdc(r.payment_usdc)}</td>
                  <td>{exactTime(r.received_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
