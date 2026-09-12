import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { DotsThreeVertical, List } from '../icons'
import { PipelineStatusMenu } from './PipelineStatusMenu'

export function Header({ onMenu }: { onMenu: () => void }) {
  const location = useLocation()
  const [now, setNow] = useState(() => new Date())

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000)
    return () => window.clearInterval(timer)
  }, [])

  const section = ({
    '/': 'Mission Control',
    '/market': 'Market',
    '/canvas': 'Market Canvas',
    '/intake': 'Knowledge intake',
    '/opportunities': 'Opportunities',
    '/regime-lab': 'Regime Lab',
    '/thesis': 'Thesis',
    '/pipeline': 'Integration Pipeline',
    '/sources': 'Sources',
    '/logs': 'Evidence Ledger',
    '/execution': 'Execution Readiness',
    '/settings': 'Settings',
  } as Record<string, string>)[location.pathname] || 'TradeSync'

  return (
    <header className="topbar">
      <div className="topbar-title-wrap">
        <button className="mobile-menu" onClick={onMenu} aria-label="Open navigation">
          <List size={22} />
        </button>
        <div className="topbar-page-title">
          <span>TradeSync</span>
          <h1>{section}</h1>
        </div>
      </div>
      <div className="topbar-meta">
        <PipelineStatusMenu />
        <time dateTime={now.toISOString()}>{now.toISOString().replace('T', ' ').slice(0, 19)} UTC</time>
        <span className="sync-state"><span className="status-dot status-dot--good" />System time synced</span>
        <button className="icon-button" aria-label="More options"><DotsThreeVertical size={20} /></button>
      </div>
    </header>
  )
}
