import { Link } from 'react-router-dom'
import { useExecutionStatus } from '../api/hooks'
import { useRehearsals } from '../api/hooks/useRehearsal'
import { useSkillGate } from '../api/hooks/useSkillGate'
import { PaperRehearsal } from '../components/PaperRehearsal'
import { WatchOnlyWallet } from '../components/WatchOnlyWallet'
import styles from './Execution.module.css'

type GateState = 'met' | 'notMet' | 'closed' | 'checking'

interface Gate {
  title: string
  requirement: string
  now: React.ReactNode
  state: GateState
  label: string
}

/**
 * Execution Readiness: what stands between paper research and a live order,
 * each gate with what it requires and what is measured now. Nothing on this
 * page can open a gate; it shows how far away that is.
 */
export function Execution() {
  const status = useExecutionStatus()
  const gate = useSkillGate()
  const rehearsals = useRehearsals(5)
  const enabled = status.data?.execution_enabled === 'true'
  const hyperliquid = status.data?.venues?.find((v) => v.venue === 'hyperliquid')
  const executorUp = hyperliquid?.circuit_open === false
  const verdict = gate.data?.verdict
  const counts = rehearsals.data?.counts

  const gates: Gate[] = [
    {
      title: 'Runtime gate stays shut',
      requirement: 'EXECUTION_ENABLED remains false until every gate below passes and the operator approves.',
      now: status.isLoading ? 'checking…' : `EXECUTION_ENABLED=${status.data?.execution_enabled ?? 'unknown'}`,
      state: status.isLoading ? 'checking' : enabled ? 'notMet' : 'closed',
      label: status.isLoading ? 'CHECKING' : enabled ? 'OPEN: REVIEW' : 'CLOSED',
    },
    {
      title: 'Demonstrated edge',
      requirement: 'At least one horizon and regime shows positive skill after the multiple-comparison adjustment and a positive mean return after fees, spread and slippage.',
      now: gate.isLoading ? 'measuring…' : verdict
        ? <>skill gate {verdict.gate} · positive skill {verdict.any_positive_skill ? 'yes' : 'no'} · economic edge {verdict.any_economic_edge ? 'yes' : 'no'} · <Link to="/regime-lab">Regime Lab</Link></>
        : 'skill gate unavailable',
      state: gate.isLoading ? 'checking' : verdict?.any_economic_edge ? 'met' : 'notMet',
      label: gate.isLoading ? 'CHECKING' : verdict?.any_economic_edge ? 'MET' : 'NOT MET',
    },
    {
      title: 'Paper rehearsal journal',
      requirement: 'Rehearsals priced from the live mark and spread, with duplicates and missing dependencies refused and journaled.',
      now: counts ? `${counts.rehearsed} rehearsed · ${counts.refused} refused` : 'journal unavailable',
      state: counts ? (counts.rehearsed > 0 ? 'met' : 'notMet') : 'checking',
      label: counts ? (counts.rehearsed > 0 ? 'MET' : 'NOT MET') : 'CHECKING',
    },
    {
      title: 'Isolated wallet and bounded signer',
      requirement: 'A separate Hyperliquid wallet whose key lives only in the signer service, provisioned by the operator.',
      now: 'watch-only address lookup; no signer provisioned',
      state: 'notMet',
      label: 'NOT MET',
    },
    {
      title: 'Executor and reconciliation',
      requirement: 'The Hyperliquid executor running with reconciliation passing against the venue.',
      now: executorUp ? 'executor responding' : 'executor not running in this runtime',
      state: executorUp ? 'met' : 'notMet',
      label: executorUp ? 'MET' : 'NOT MET',
    },
    {
      title: 'Single-use approval and canary limits',
      requirement: 'Every order consumes one ChaseOS approval once; a pilot starts with hard notional, symbol, leverage and loss ceilings.',
      now: 'no live approval issued; canary limits not configured',
      state: 'notMet',
      label: 'NOT MET',
    },
  ]
  const met = gates.filter((g) => g.state === 'met').length
  const required = gates.length - 1

  return (
    <div className={styles.page}>
      <section className={`panel ${styles.hero}`}>
        <div>
          <h2>Execution Readiness</h2>
          <p>What stands between paper research and a live order, measured now. Nothing here can open a gate; live execution needs every gate met and an explicit operator decision.</p>
        </div>
        <div style={{ display: 'grid', gap: 8, justifyItems: 'end' }}>
          <span className={styles.state}>{enabled ? 'CONFIGURATION CONFLICT' : 'FAIL-CLOSED'}</span>
          <span className={styles.progress}>
            {met} of {required} gates met
            <span className={styles.progressBar}><span style={{ width: `${(met / required) * 100}%` }} /></span>
          </span>
        </div>
      </section>

      <section className="panel">
        <div className="panel-heading"><div><h3>Gates</h3><p>requirement, and what the system measures right now</p></div></div>
        <ol className={styles.gates}>
          {gates.map((g, i) => (
            <li key={g.title} className={styles.gate}>
              <span className={styles.num}>{i + 1}</span>
              <div><p className={styles.title}>{g.title}</p><p className={styles.req}>{g.requirement}</p></div>
              <div className={styles.now}>{g.now}</div>
              <span className={`${styles.status} ${styles[g.state]}`}>{g.label}</span>
            </li>
          ))}
        </ol>
      </section>

      <div className={styles.split}>
        <WatchOnlyWallet />
        <PaperRehearsal />
      </div>

      <section className={`panel ${styles.foot}`}>
        <span>Evidence before authority: every decision, rehearsal and refusal is kept in the ledger.</span>
        <Link to="/logs">Open evidence ledger →</Link>
      </section>

      {status.isError && <section className="panel" style={{ padding: 14 }}><span className="tone-bad">Execution status endpoint unavailable. The system remains fail-closed.</span></section>}
    </div>
  )
}
