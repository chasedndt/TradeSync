import { useEffect, useState } from 'react'
import { NavLink } from 'react-router-dom'
import {
  Bell,
  CaretLeft,
  CaretRight,
  ChartBar,
  ChartLineUp,
  BracketsCurly,
  Database,
  FlowArrow,
  Gauge,
  Gear,
  ListChecks,
  Robot,
  ShieldCheck,
  SignOut,
  Target,
  UserCircle,
  X,
} from '../icons'
import { useIntegrationPipeline } from '../../api/hooks'

const navItems = [
  { to: '/', label: 'Mission Control', description: 'Market, opportunities, and health.', icon: Target, end: true },
  { to: '/thesis', label: 'Thesis', description: 'Daily editions and the live thesis.', icon: ListChecks },
  { to: '/market', label: 'Market', description: 'Hyperliquid market evidence.', icon: ChartBar },
  { to: '/canvas', label: 'Market Canvas', description: 'Candles with recorded paper evidence.', icon: ChartLineUp },
  { to: '/opportunities', label: 'Opportunities', description: 'Ranked paper research setups.', icon: ChartLineUp },
  { to: '/agents', label: 'Agents', description: 'What the ChaseOS fleet is saying.', icon: Robot },
  { to: '/fleet', label: 'Fleet', description: 'Hermes jobs: cadence, cost, directives.', icon: Gauge },
  { to: '/regime-lab', label: 'Regime Lab', description: 'Feature evidence and rulebook experiments.', icon: BracketsCurly },
  { to: '/pipeline', label: 'Integration pipeline', description: 'Live dependencies and recovery targets.', icon: FlowArrow },
  { to: '/intake', label: 'Knowledge intake', description: 'Held connector submissions.', icon: Database },
  { to: '/sources', label: 'Sources', description: 'Legacy source intake surface.', icon: Database },
  { to: '/logs', label: 'Evidence ledger', description: 'Decisions, orders, and receipts.', icon: ListChecks },
  { to: '/execution', label: 'Execution readiness', description: 'Fail-closed wallet and policy gates.', icon: ShieldCheck },
]

const EXPANDED_KEY = 'tradesync.sidebar.expanded'

interface SidebarProps {
  open: boolean
  onClose: () => void
}

/**
 * The rail. Two widths: icons only, or expanded with every label visible.
 * The choice is remembered per browser. The nav scrolls on its own, so a
 * short window still reaches the last entry.
 */
export function Sidebar({ open, onClose }: SidebarProps) {
  const { data: pipeline } = useIntegrationPipeline()
  const pipelineTone = pipeline?.tier_a.status === 'ready' ? 'good' : pipeline?.tier_a.status === 'offline' ? 'bad' : 'warn'
  const [expanded, setExpanded] = useState<boolean>(() => {
    try { return localStorage.getItem(EXPANDED_KEY) === '1' } catch { return false }
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
        <button
          type="button"
          className="sidebar-toggle"
          onClick={() => setExpanded(!expanded)}
          aria-label={expanded ? 'Collapse navigation to icons' : 'Expand navigation to show labels'}
          title={expanded ? 'Collapse' : 'Expand'}
        >
          {expanded ? <CaretLeft size={16} weight="bold" /> : <CaretRight size={16} weight="bold" />}
        </button>
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
                  {to === '/pipeline' && pipeline && <em>Tier A {pipeline.tier_a.status} · {pipeline.tier_a.ready_count}/{pipeline.tier_a.total_count} ready</em>}
                </span>
              )}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <button className="nav-link" title="Notifications" aria-label="Notifications">
            <span className="notification-wrap"><Bell size={22} /><span className="notification-dot" /></span>
            <span className="sidebar-label"><span className="sidebar-label-title">Notifications</span></span>
          </button>
          <NavLink to="/settings" onClick={onClose} className={({ isActive }) => `nav-link ${isActive ? 'nav-link--active' : ''}`} title="Settings">
            <Gear size={22} />
            <span className="sidebar-label"><span className="sidebar-label-title">Settings</span></span>
          </NavLink>
          <button className="nav-link" title="Operator profile" aria-label="Operator profile">
            <UserCircle size={22} />
            <span className="sidebar-label"><span className="sidebar-label-title">Operator</span></span>
          </button>
          <button className="nav-link sidebar-mobile-only" title="Exit" aria-label="Exit">
            <SignOut size={22} />
            <span className="sidebar-label"><span className="sidebar-label-title">Exit</span></span>
          </button>
        </div>
      </aside>
    </>
  )
}
