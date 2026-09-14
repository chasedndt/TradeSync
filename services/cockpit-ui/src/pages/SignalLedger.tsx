import { useForwardTest, useLabHealth } from '../api/hooks/useStrikeZone'
import { EquityCurve } from '../components/ledger/EquityCurve'
import { ForwardMatrix } from '../components/ledger/ForwardMatrix'
import { LabHealth } from '../components/ledger/LabHealth'
import { TradeResearch } from '../components/ledger/TradeResearch'
import { ManagedPaper } from '../components/ledger/ManagedPaper'
import { SourceComparison } from '../components/ledger/SourceComparison'
import { ResearchTrials } from '../components/ledger/ResearchTrials'
import { LedgerTable } from '../components/ledger/LedgerTable'
import { Scorecards } from '../components/ledger/Scorecards'
import { minutesAgo } from '../components/ledger/format'
import styles from './SignalLedger.module.css'

/**
 * The StrikeZone quant lab, moved in from Discord: the closed-candle forward
 * test as a ledger, paper equity after costs, daily scorecards and regime
 * cohorts, and the lab's health with the reason each job failed. Paper-only.
 */
export function SignalLedger() {
  const forward = useForwardTest()
  const health = useLabHealth()
  const f = forward.data
  const h = health.data
  const integrity = h ? (h.ok === true ? 'OK' : h.ok === false ? `HOLD · ${h.issues.length}` : 'NO REPORT') : '—'
  const integrityTone = h?.ok === true ? 'tone-good' : h?.ok === false ? 'tone-warn' : 'tone-dim'
  const lastCallStale = (f?.totals.last_signal_age_minutes ?? 0) > 75

  return (
    <div className={styles.page}>
      <section className={`panel ${styles.hero}`}>
        <div>
          <div className={styles.kicker}>StrikeZone quant lab · Hermes fleet · paper only</div>
          <h2>Signal Ledger</h2>
          <p>
            The closed-candle forward test on Hyperliquid as the lab records it: every call with its levels, each paper trade's outcome after fees,
            slippage and funding, the daily scorecards, and the lab's own integrity checks. These are the records the Discord channels announced.
            Nothing here can promote a strategy or place an order.
          </p>
        </div>
        <div className={styles.stats}>
          <div className={styles.stat}><span>last call</span><strong className={lastCallStale ? 'tone-warn' : undefined}>{f ? minutesAgo(f.totals.last_signal_age_minutes) : '—'}</strong></div>
          <div className={styles.stat}><span>integrity</span><strong className={integrityTone}><a href="#lab-health">{integrity}</a></strong></div>
          <div className={styles.stat}><span>failing jobs</span><strong className={h?.failing_jobs ? 'tone-bad' : 'tone-good'}>{h ? h.failing_jobs : '—'}</strong></div>
          <div className={styles.stat}><span>calls</span><strong>{f ? f.totals.signals.toLocaleString() : '—'}</strong></div>
          <div className={styles.stat}><span>trades · resolved</span><strong>{f ? `${f.totals.trades} · ${f.totals.outcomes}` : '—'}</strong></div>
          <div className={styles.stat}><span>open · overdue</span><strong className={f?.totals.overdue ? 'tone-bad' : undefined}>{f ? `${f.totals.open} · ${f.totals.overdue}` : '—'}</strong></div>
        </div>
      </section>

      {forward.isError && <section className="panel"><p className={styles.message}>Forward test unavailable from the state API.</p></section>}
      {f && f.totals.signals === 0 && (
        <section className="panel"><p className={styles.message}>No ledger rows yet. The StrikeZone quant bridge posts the lab's files every five minutes.</p></section>
      )}
      {f && f.cells.length > 0 && <ForwardMatrix data={f} />}
      {f && f.equity.trades > 0 && <EquityCurve equity={f.equity} notional={f.paper_notional_usdc} />}
      <ManagedPaper />
      <SourceComparison />
      <ResearchTrials />
      <TradeResearch />
      <LedgerTable assets={f?.assets ?? []} timeframes={f?.timeframes ?? []} />
      <Scorecards />
      {h && <LabHealth data={h} />}
      {f && <p className={styles.note}>{f.methodology_version ?? 'no methodology'} · strategy {f.strategy_version ?? '—'} · {f.note}</p>}
    </div>
  )
}
