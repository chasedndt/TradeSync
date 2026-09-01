import { NavLink } from 'react-router-dom'
import {
  Bell,
  ChartBar,
  ChartLineUp,
  Database,
  Gear,
  ListChecks,
  ShieldCheck,
  SignOut,
  Target,
  UserCircle,
  X,
} from '../icons'

const navItems = [
  { to: '/', label: 'Mission Control', icon: Target, end: true },
  { to: '/market', label: 'Market', icon: ChartBar },
  { to: '/opportunities', label: 'Opportunities', icon: ChartLineUp },
  { to: '/sources', label: 'Sources', icon: Database },
  { to: '/logs', label: 'Evidence ledger', icon: ListChecks },
  { to: '/execution', label: 'Execution readiness', icon: ShieldCheck },
]

interface SidebarProps {
  open: boolean
  onClose: () => void
}

export function Sidebar({ open, onClose }: SidebarProps) {
  return (
    <>
      {open && <button className="sidebar-backdrop" aria-label="Close navigation" onClick={onClose} />}
      <aside className={`sidebar ${open ? 'sidebar--open' : ''}`} aria-label="Primary navigation">
        <div className="sidebar-brand">
          <span className="brand-mark" aria-hidden="true">TS</span>
          <span className="sidebar-label brand-name">TradeSync</span>
          <button className="sidebar-close" onClick={onClose} aria-label="Close navigation">
            <X size={20} />
          </button>
        </div>
        <nav className="sidebar-nav">
          {navItems.map(({ to, label, icon: Icon, end }) => (
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
              <span className="sidebar-label">{label}</span>
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
