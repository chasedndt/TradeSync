import { NavLink } from 'react-router-dom'
import {
  Bell,
  ChartBar,
  ChartLineUp,
  BracketsCurly,
  Database,
  FlowArrow,
  Gear,
  ListChecks,
  ShieldCheck,
  SignOut,
  Target,
  UserCircle,
  X,
} from '../icons'
import { useIntegrationPipeline } from '../../api/hooks'

const navItems = [
  { to: '/', label: 'Mission Control', description: 'Market, opportunities, and health.', icon: Target, end: true },
  { to: '/market', label: 'Market', description: 'Hyperliquid market evidence.', icon: ChartBar },
  { to: '/canvas', label: 'Market Canvas', description: 'Candles with recorded paper evidence.', icon: ChartLineUp },
  { to: '/opportunities', label: 'Opportunities', description: 'Ranked paper research setups.', icon: ChartLineUp },
  { to: '/regime-lab', label: 'Regime Lab', description: 'Feature evidence and rulebook experiments.', icon: BracketsCurly },
  { to: '/pipeline', label: 'Integration pipeline', description: 'Live dependencies, missing links, and restart targets.', icon: FlowArrow },
  { to: '/intake', label: 'Knowledge intake', description: 'Quarantined connector submissions awaiting review.', icon: Database },
  { to: '/sources', label: 'Sources', description: 'Legacy source intake surface.', icon: Database },
  { to: '/logs', label: 'Evidence ledger', description: 'Decisions, orders, and receipts.', icon: ListChecks },
  { to: '/execution', label: 'Execution readiness', description: 'Fail-closed wallet and policy gates.', icon: ShieldCheck },
]

interface SidebarProps {
  open: boolean
  onClose: () => void
}

export function Sidebar({ open, onClose }: SidebarProps) {
  const { data: pipeline } = useIntegrationPipeline()
  const pipelineTone = pipeline?.tier_a.status === 'ready' ? 'good' : pipeline?.tier_a.status === 'offline' ? 'bad' : 'warn'

  return (
    <>
      {open && <button className="sidebar-backdrop" aria-label="Close navigation" onClick={onClose} />}
      <aside className={`sidebar ${open ? 'sidebar--open' : ''}`} aria-label="Primary navigation">
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
              title={label}
              className={({ isActive }) => `nav-link ${isActive ? 'nav-link--active' : ''}`}
            >
              <Icon size={23} weight="regular" aria-hidden="true" />
              {to === '/pipeline' && <i className={`nav-status-dot status-dot status-dot--${pipelineTone}`} />}
              <span className="sidebar-label">{label}</span>
              <span className="nav-hover-card" role="tooltip">
                <strong>{label}</strong>
                <small>{description}</small>
                {to === '/pipeline' && pipeline && <em>Tier A {pipeline.tier_a.status} · {pipeline.tier_a.ready_count}/{pipeline.tier_a.total_count} ready</em>}
              </span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <button className="nav-link" title="Notifications" aria-label="Notifications">
            <span className="notification-wrap"><Bell size={22} /><span className="notification-dot" /></span>
            <span className="sidebar-label">Notifications</span>
          </button>
          <NavLink to="/settings" onClick={onClose} className={({ isActive }) => `nav-link ${isActive ? 'nav-link--active' : ''}`} title="Settings">
            <Gear size={23} />
            <span className="sidebar-label">Settings</span>
          </NavLink>
          <button className="nav-link" title="Operator profile" aria-label="Operator profile">
            <UserCircle size={23} />
            <span className="sidebar-label">Operator</span>
          </button>
          <button className="nav-link sidebar-mobile-only" title="Exit" aria-label="Exit">
            <SignOut size={23} />
            <span className="sidebar-label">Exit</span>
          </button>
        </div>
      </aside>
    </>
  )
}
