import { NavLink } from 'react-router-dom'
import type { Opportunity } from '../../api/types'
import { formatAge } from './format'
import { QuietState } from './QuietState'
import styles from './Home.module.css'

function expiresIn(opportunity: Opportunity): string {
  if (!opportunity.expires_at) return '—'
  const seconds = (Date.parse(opportunity.expires_at) - Date.now()) / 1000
  if (seconds <= 0) return 'expiring'
  return seconds < 60 ? 'under 1m' : `in ${Math.floor(seconds / 60)}m`
}

/** Live paper opportunities across every market, full width. The API returns only unexpired ones. */
export function OpportunitiesPanel({ opps, loading }: { opps: Opportunity[]; loading: boolean }) {
  return (
    <section className="panel" aria-labelledby="paper-opps-title">
      <div className="panel-heading">
        <div><h2 id="paper-opps-title">Paper Opportunities</h2><p>{loading ? 'checking…' : `${opps.length} live · not managed positions · newest first`}</p></div>
        <div className="panel-actions">
          <NavLink to="/opportunities?view=learning" className="panel-action">Learning →</NavLink>
          <NavLink to="/opportunities" className="panel-action">All opportunities →</NavLink>
        </div>
      </div>
      {loading ? (
        <p className="tone-dim" style={{ padding: '10px 17px 14px', margin: 0, fontSize: 12 }}>Checking scoring output…</p>
      ) : opps.length === 0 ? (
        <QuietState />
      ) : (
        <div className="table-scroll">
          <table className={styles.opps}>
            <thead>
              <tr><th>Side</th><th>Market</th><th>Bias</th><th>Quality</th><th>Timeframe</th><th>Opened</th><th>Expires</th><th /></tr>
            </thead>
            <tbody>
              {opps.slice(0, 12).map((o) => (
                <tr key={o.id}>
                  <td><span className={`pill ${o.dir === 'LONG' ? 'pill--good' : 'pill--bad'}`}>{o.dir}</span></td>
                  <td><strong>{o.symbol.replace('-PERP', '')}</strong></td>
                  <td className={o.bias >= 0 ? 'tone-good' : 'tone-bad'}>{o.bias >= 0 ? '+' : ''}{o.bias.toFixed(2)}</td>
                  <td>{Math.round(o.quality)}</td>
                  <td>{o.timeframe}</td>
                  <td>{formatAge((Date.now() - new Date(o.snapshot_ts).getTime()) / 1000)}</td>
                  <td>{expiresIn(o)}</td>
                  <td><NavLink className={styles.oppLink} to={`/opportunities/${o.id}`}>Inspect →</NavLink></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
