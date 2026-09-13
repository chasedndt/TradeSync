import { NavLink } from 'react-router-dom'
import type { Opportunity } from '../../api/types'
import { formatAge } from './format'
import styles from './Home.module.css'

/** Open paper opportunities across every market, full width. */
export function OpportunitiesPanel({ opps, loading }: { opps: Opportunity[]; loading: boolean }) {
  return (
    <section className="panel" aria-labelledby="paper-opps-title">
      <div className="panel-heading">
        <div><h2 id="paper-opps-title">Paper Opportunities</h2><p>{loading ? 'checking…' : `${opps.length} open · paper only · newest first`}</p></div>
        <NavLink to="/opportunities" className="panel-action">All opportunities →</NavLink>
      </div>
      {opps.length === 0 ? (
        <p className="tone-dim" style={{ padding: '10px 17px 14px', margin: 0, fontSize: 12 }}>
          {loading ? 'Checking scoring output…' : 'No open paper opportunity. The scorer records a verdict every cycle; one appears when a side is admitted.'}
        </p>
      ) : (
        <div className="table-scroll">
          <table className={styles.opps}>
            <thead>
              <tr><th>Side</th><th>Market</th><th>Bias</th><th>Quality</th><th>Timeframe</th><th>Status</th><th>Opened</th><th /></tr>
            </thead>
            <tbody>
              {opps.slice(0, 12).map((o) => (
                <tr key={o.id}>
                  <td><span className={`pill ${o.dir === 'LONG' ? 'pill--good' : 'pill--bad'}`}>{o.dir}</span></td>
                  <td><strong>{o.symbol.replace('-PERP', '')}</strong></td>
                  <td className={o.bias >= 0 ? 'tone-good' : 'tone-bad'}>{o.bias >= 0 ? '+' : ''}{o.bias.toFixed(2)}</td>
                  <td>{Math.round(o.quality)}</td>
                  <td>{o.timeframe}</td>
                  <td>{o.status}</td>
                  <td>{formatAge((Date.now() - new Date(o.snapshot_ts).getTime()) / 1000)}</td>
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
