import { useEffect, useState } from 'react'
import { NavLink } from 'react-router-dom'
import {
  CaretDoubleLeft,
  CaretDoubleRight,
  ChartBar,
  ChartLineUp,
  BracketsCurly,
  Database,
  Flask,
  FlowArrow,
  Gauge,
  ListChecks,
  Robot,
  ShieldCheck,
  Target,
  X,
} from '../icons'
import { useIntegrationPipeline } from '../../api/hooks'

const navItems = [
  { to: '/', label: 'Mission Control', description: 'Thesis, market, opportunities, health.', icon: Target, end: true },
  { to: '/thesis', label: 'Market thesis', description: 'Editions, outlook and the live read.', icon: ListChecks },
  { to: '/market', label: 'Market', description: 'Hyperliquid market evidence.', icon: ChartBar },
  { to: '/canvas', label: 'Market Canvas', description: 'Candles with recorded paper evidence.', icon: ChartLineUp },
  { to: '/opportunities', label: 'Opportunities', description: 'Ranked paper research setups.', icon: ChartLineUp },
  { to: '/signal-ledger', label: 'Signal ledger', description: 'StrikeZone forward test, outcomes, scorecards.', icon: Flask },
  { to: '/agents', label: 'Hermes & agents', description: 'Gateway status, jobs, fleet output.', icon: Robot },
  { to: '/fleet', label: 'Fleet', description: 'Every Hermes job: cadence, cost.', icon: Gauge },
  { to: '/regime-lab', label: 'Regime Lab', description: 'Feature evidence and rulebook experiments.', icon: BracketsCurly },
  { to: '/pipeline', label: 'Integration pipeline', description: 'Live dependencies and recovery targets.', icon: FlowArrow },
  { to: '/intake', label: 'Knowledge intake', description: 'Held connector submissions.', icon: Database },
  { to: '/logs', label: 'Evidence ledger', description: 'Decisions, orders, and receipts.', icon: ListChecks },
  { to: '/execution', label: 'Execution readiness', description: 'Fail-closed wallet and policy gates.', icon: ShieldCheck },
]

const EXPANDED_KEY = 'tradesync.sidebar.expanded'

interface SidebarProps {
  open: boolean
  onClose: () => void
}

/**
 * The rail: icons only, or expanded with every label beside its icon. The
 * expand control is a full-width bar at the foot of the rail. The nav
 * scrolls on its own, so a short window still reaches the last entry. This
 * is a single-operator workstation: no notifications, profile or sign-out.
 */
export function Sidebar({ open, onClose }: SidebarProps) {
  const { data: pipeline } = useIntegrationPipeline()
  const pipelineTone = pipeline?.tier_a.status === 'ready' ? 'good' : pipeline?.tier_a.status === 'offline' ? 'bad' : 'warn'
  const [expanded, setExpanded] = useState<boolean>(() => {
    try { return localStorage.getItem(EXPANDED_KEY) !== '0' } catch { return true }
  })
  useEffect(() => {
    try { localStorage.setItem(EXPANDED_KEY, expanded ? '1' : '0') } catch { /* private window */ }
    document.documentElement.classList.toggle('sidebar-expanded', expanded)
  }, [expanded])

  return (
    <>
      {open && <button className="sidebar-backdrop" aria-label="Close navigation" onClick={onClose} />}
      <aside className={`sidebar ${open ? 'sidebar--open' : ''} ${expanded ? 'sidebar--expanded' : ''}`} aria-label="Primary navigation">
        <div className="sidebar-brand">
          <img className="brand-mark" src="/brand/tradesync-mark.png" alt="TradeSync" />
          <span className="sidebar-label brand-name">TradeSync</span>
          <button className="sidebar-close" onClick={onClose} aria-label="Close navigation">
            <X size={20} />
          </button>
        </div>
        <nav className="sidebar-nav">
          {navItems.map(({ to, label, description, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              onClick={onClose}
              aria-label={label}
              title={expanded ? undefined : label}
              className={({ isActive }) => `nav-link ${isActive ? 'nav-link--active' : ''}`}
            >
              <Icon size={22} weight="regular" aria-hidden="true" />
              {to === '/pipeline' && <i className={`nav-status-dot status-dot status-dot--${pipelineTone}`} />}
              <span className="sidebar-label">
                <span className="sidebar-label-title">{label}</span>
                <span className="sidebar-label-desc">{description}</span>
              </span>
              {!expanded && (
                <span className="nav-hover-card" role="tooltip">
                  <strong>{label}</strong>
                  <small>{description}</small>
                </span>
              )}
            </NavLink>
          ))}
        </nav>
        <button
          type="button"
          className="sidebar-expand"
          onClick={() => setExpanded(!expanded)}
          aria-label={expanded ? 'Collapse navigation to icons' : 'Expand navigation to show labels'}
          title={expanded ? 'Collapse' : 'Expand'}
        >
          {expanded ? <CaretDoubleLeft size={16} weight="bold" /> : <CaretDoubleRight size={16} weight="bold" />}
          <span className="sidebar-label"><span className="sidebar-label-title">Collapse</span></span>
        </button>
      </aside>
    </>
  )
}
