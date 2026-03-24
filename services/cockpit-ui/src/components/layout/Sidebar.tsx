import { NavLink } from 'react-router-dom'

const navItems = [
  { to: '/', label: 'Overview' },
  { to: '/opportunities', label: 'Opportunities' },
  { to: '/market', label: 'Market' },
  { to: '/execution', label: 'Execution' },
  { to: '/positions', label: 'Positions' },
  { to: '/sources', label: 'Sources Library' },
  { to: '/copilot', label: 'Copilot' },
  { to: '/autonomy', label: 'Autonomy' },
  { to: '/logs', label: 'Decisions & Orders' },
  { to: '/risk-policies', label: 'Risk Policies' },
]

export function Sidebar() {
  return (
    <aside className="w-56 bg-gray-800 border-r border-gray-700 flex flex-col">
      <div className="p-4 border-b border-gray-700">
        <h1 className="text-lg font-bold">TradeSync</h1>
        <span className="text-xs text-gray-400">Cockpit</span>
      </div>
      <nav className="flex-1 p-2 overflow-y-auto">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `block px-3 py-2 rounded text-sm ${isActive
                ? 'bg-gray-700 text-white'
                : 'text-gray-300 hover:bg-gray-700 hover:text-white'
              }`
            }
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
      <div className="p-2 border-t border-gray-700">
        <NavLink
          to="/settings"
          className={({ isActive }) =>
            `block px-3 py-2 rounded text-sm ${isActive
              ? 'bg-gray-700 text-white'
              : 'text-gray-300 hover:bg-gray-700 hover:text-white'
            }`
          }
        >
          Settings
        </NavLink>
      </div>
    </aside>
  )
}
