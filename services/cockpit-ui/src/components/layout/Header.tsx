import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { DotsThreeVertical, List } from '../icons'

export function Header({ onMenu }: { onMenu: () => void }) {
  const location = useLocation()
  const [now, setNow] = useState(() => new Date())

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000)
    return () => window.clearInterval(timer)
  }, [])

  const section = location.pathname === '/regime-lab' ? 'Regime Lab' : 'Mission Control'

  return (
    <header className="topbar">
      <div className="topbar-title-wrap">
        <button className="mobile-menu" onClick={onMenu} aria-label="Open navigation">
          <List size={22} />
        </button>
        <h1>TradeSync</h1>
        <span>{section}</span>
      </div>
      <div className="topbar-meta">
        <time dateTime={now.toISOString()}>{now.toISOString().replace('T', ' ').slice(0, 19)} UTC</time>
        <span className="sync-state"><span className="status-dot status-dot--good" />System time synced</span>
        <button className="icon-button" aria-label="More options"><DotsThreeVertical size={20} /></button>
      </div>
    </header>
  )
}
