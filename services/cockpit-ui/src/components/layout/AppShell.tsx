import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { Header } from './Header'

export function AppShell() {
  const [menuOpen, setMenuOpen] = useState(false)

  return (
    <div className="app-shell">
      <Sidebar open={menuOpen} onClose={() => setMenuOpen(false)} />
      <div className="app-frame">
        <Header onMenu={() => setMenuOpen(true)} />
        <main className="app-main">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
