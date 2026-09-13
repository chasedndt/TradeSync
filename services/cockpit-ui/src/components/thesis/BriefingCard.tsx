import type { HermesBriefing } from '../../api/types'
import styles from './Thesis.module.css'

/** The briefing Hermes drafted from the measured outlook. Advisory; filed in quarantine with a receipt. */
export function BriefingCard({ b }: { b: HermesBriefing | null }) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h3>Hermes briefing</h3>
          <p>drafted from the measured outlook · advisory only · cannot score, approve or execute</p>
        </div>
        {b?.status === 'ok' && <span className="metric-sub">{b.model} · {Math.round((b.elapsed_ms ?? 0) / 1000)}s</span>}
      </div>
      <div className={styles.briefing}>
        {!b && <p className="tone-dim">This edition predates the Hermes briefing.</p>}
        {b?.status === 'ok' && <p>{b.content}</p>}
        {b?.status === 'refused' && <p className="tone-bad">The answer was refused at the boundary: {b.detail}</p>}
        {b?.status === 'unavailable' && <p className="tone-warn">Hermes did not answer in time ({b.detail}); the rest of the edition stands.</p>}
        {b?.status === 'not_configured' && <p className="tone-dim">The Hermes connector is not configured.</p>}
        {b?.receipt?.content_digest && <span className="metric-sub">quarantine receipt {b.receipt.content_digest.slice(0, 16)}…</span>}
      </div>
    </section>
  )
}
