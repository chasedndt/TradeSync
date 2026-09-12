import { Link } from 'react-router-dom'
import { WatchOnlyWallet } from '../components/WatchOnlyWallet'
import { useExecutionStatus } from '../api/hooks'
import { Database, ListChecks, LockKey, Prohibit, ShieldCheck, Wallet } from '../components/icons'

export function Execution() {
  const { data: status, isLoading, error } = useExecutionStatus()
  const backendDisabled = status?.execution_enabled !== 'true'
  const hyperliquid = status?.venues?.find((venue) => venue.venue === 'hyperliquid')

  return (
    <div className="mission-control">
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Execution Readiness</h2>
            <p>Read-only view of the paper execution boundary</p>
          </div>
          <span className="tone-bad">DISABLED</span>
        </div>
        <div className="execution-card">
          <Prohibit size={42} className="tone-bad" weight="bold" />
          <div><h3>{backendDisabled ? 'LIVE EXECUTION DISABLED' : 'CONFIGURATION CONFLICT'}</h3><strong>TradeSync is operating without wallet authority.</strong></div>
          <ul className="execution-list">
            <li>Account viewing does not grant signing or order authority</li>
            <li>No order-placement controls are exposed</li>
            <li>Context providers cannot approve or execute trades</li>
          </ul>
        </div>
      </section>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <section className="panel p-5">
          <ShieldCheck size={28} className="tone-good mb-4" weight="duotone" />
          <div className="eyebrow">Runtime gate</div>
          <div className={`text-lg font-bold ${backendDisabled ? 'tone-good' : 'tone-bad'}`}>{isLoading ? 'CHECKING' : backendDisabled ? 'FAIL-CLOSED' : 'REVIEW REQUIRED'}</div>
          <p className="text-xs text-slate-400 mt-2">Backend reports EXECUTION_ENABLED={status?.execution_enabled ?? 'unknown'}.</p>
        </section>
        <section className="panel p-5">
          <Wallet size={28} className="tone-dim mb-4" weight="duotone" />
          <div className="eyebrow">Wallet authority</div>
          <div className="text-lg font-bold tone-dim">WATCH ONLY</div>
          <p className="text-xs text-slate-400 mt-2">Public-address lookup below. Signer provisioning and activation remain separate approval-gated operations.</p>
        </section>
        <section className="panel p-5">
          <Database size={28} className="tone-warn mb-4" weight="duotone" />
          <div className="eyebrow">Hyperliquid executor</div>
          <div className="text-lg font-bold tone-warn">{hyperliquid?.circuit_open === false ? 'RESPONDING' : 'NOT RUNNING'}</div>
          <p className="text-xs text-slate-400 mt-2">The lean dashboard stack does not start the optional paper executor.</p>
        </section>
      </div>

      <WatchOnlyWallet />
      <section className="panel">
        <div className="panel-heading"><div><h2>Activation gates</h2><p>These are safety requirements, not controls</p></div></div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-px bg-slate-800">
          {[
            ['1', 'Paper evidence', 'End-to-end paper receipts, replay protection, and journal accuracy must pass.'],
            ['2', 'Isolated wallet', 'A separate Hyperliquid wallet and bounded signer require explicit operator approval.'],
            ['3', 'Approval consumption', 'Every approved trade must be single-use, attributable, and durably recorded.'],
            ['4', 'Canary limits', 'Any live pilot starts with hard notional, symbol, leverage, and loss ceilings.'],
          ].map(([number, title, copy]) => (
            <div key={number} className="bg-[#0d1928] p-5 flex gap-4">
              <span className="font-mono tone-dim">{number}</span>
              <div><h3 className="m-0 text-sm font-semibold">{title}</h3><p className="m-0 mt-2 text-xs text-slate-400 leading-5">{copy}</p></div>
            </div>
          ))}
        </div>
      </section>

      <section className="panel p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-start gap-3"><LockKey size={23} className="tone-info" /><div><strong className="text-sm">Evidence before authority</strong><p className="m-0 mt-1 text-xs text-slate-400">Review the immutable decision and order ledger before any future activation discussion.</p></div></div>
        <Link className="text-xs text-blue-400 hover:text-blue-300 inline-flex items-center gap-2" to="/logs"><ListChecks size={17} />Open evidence ledger</Link>
      </section>

      {error && <div className="panel p-4 text-sm tone-bad">Execution status endpoint is unavailable. The UI remains fail-closed.</div>}
    </div>
  )
}
