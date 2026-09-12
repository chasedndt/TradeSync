import type { ThesisResponse } from '../api/types'
import styles from './Thesis.module.css'

const num = (v: number | null | undefined, digits = 2) => (v == null ? '—' : v.toLocaleString('en-US', { maximumFractionDigits: digits, minimumFractionDigits: digits }))
const signed = (v: number | null | undefined) => (v == null ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(2)}`)
const age = (ms: number | null | undefined) => (ms == null ? 'age unknown' : ms < 60_000 ? `${Math.round(ms / 1000)}s old` : `${Math.round(ms / 60_000)}m old`)

function Part({ title, sub, children }: { title: string; sub?: string; children: React.ReactNode }) {
  return (
    <section className={`panel ${styles.part}`}>
      <div className="panel-heading"><div><h3>{title}</h3>{sub && <p>{sub}</p>}</div></div>
      <div className={styles.partBody}>{children}</div>
    </section>
  )
}

export function ThesisText({ thesis, updatedAt }: { thesis: ThesisResponse; updatedAt: number }) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h2>Thesis · {thesis.symbol}</h2>
          <p>{thesis.visibility} · schema {thesis.schema_version} · generated {new Date(thesis.generated_at_ms).toUTCString()} · read {age(Date.now() - updatedAt)}</p>
        </div>
        <span className={thesis.freshness.stale ? 'tone-bad' : 'tone-good'}>{thesis.freshness.stale ? 'STALE EVIDENCE' : 'evidence current'}</span>
      </div>
      <div className={styles.text}>
        {thesis.lines.map((line, i) => (
          <div className={styles.line} key={i}>
            <p>{line.text}</p>
            <small>{line.source}{line.age_ms != null ? ` · ${age(line.age_ms)}` : ''}</small>
          </div>
        ))}
      </div>
      <p className={styles.foot}>{thesis.note}</p>
    </section>
  )
}

export function Structure({ thesis }: { thesis: ThesisResponse }) {
  const s = thesis.structure
  return (
    <Part title="Chart structure" sub="entry-time regime and the paper read">
      <div className={styles.row}><span>Entry regime</span><span className={styles.mono}>{s.entry_regime}{s.trailing_return_pct != null ? ` (${signed(s.trailing_return_pct)}% / ${s.lookback_minutes ?? '—'}m)` : ''}</span></div>
      <div className={styles.row}><span>Direction</span><span className={`${styles.mono} ${s.direction === 'LONG' ? 'tone-good' : s.direction === 'SHORT' ? 'tone-bad' : 'tone-dim'}`}>{s.direction}</span></div>
      <div className={styles.row}><span>Directional score</span><span className={styles.mono}>{signed(s.directional_score)}</span></div>
    </Part>
  )
}

export function Anchors({ thesis }: { thesis: ThesisResponse }) {
  const a = thesis.anchors
  const inv = thesis.invalidation
  return (
    <Part title="Anchor levels and invalidation" sub={`${a.source ?? 'candles'} · ${a.candles} buckets of ${a.bucket_s}s`}>
      {(['24h', '4h', '1h'] as const).map((w) => (
        <div className={styles.row} key={w}>
          <span>{w} range{a[`covered_${w}`] === false ? ' (partial)' : ''}</span>
          <span className={styles.mono}>{num(a[`low_${w}`])} – {num(a[`high_${w}`])}</span>
        </div>
      ))}
      <div className={styles.row}><span>Last close</span><span className={styles.mono}>{num(a.last_close)}</span></div>
      <div className={styles.row}><span>Invalidation</span><span className={`${styles.mono} tone-warn`}>{inv.level == null ? '—' : num(inv.level)}</span></div>
      <p className={styles.detail} style={{ margin: 0 }}>{inv.rule}</p>
    </Part>
  )
}

export function Derivatives({ thesis }: { thesis: ThesisResponse }) {
  const fmt = (d: ThesisResponse['derivatives'][number]) => {
    if (d.value == null) return 'absent'
    const u = d.unit ?? ''
    if (u === 'basis_points') return `${signed(d.value)} bps`
    if (u.startsWith('percent')) return `${signed(d.value)}%`
    if (u.startsWith('decimal_rate') || u.startsWith('rate_per')) return `${d.value * 100 >= 0 ? '+' : ''}${(d.value * 100).toFixed(4)}%`
    if (u.startsWith('decimal_APR')) return `${(d.value * 100).toFixed(1)}% APR`
    if (u === 'USD_delta') return `${d.value >= 0 ? '+' : ''}${Math.round(d.value).toLocaleString('en-US')} USD`
    return signed(d.value)
  }
  return (
    <Part title="Derivatives and context" sub="current readings; context-only ones score nothing">
      {thesis.derivatives.map((d) => (
        <div className={styles.row} key={d.feature_id}>
          <span>{d.label}{d.scoring_allowed ? '' : ' · context'}</span>
          <span className={`${styles.mono} ${d.value == null ? 'tone-dim' : ''}`} title={d.age_ms != null ? age(d.age_ms) : 'no observation'}>{fmt(d)}</span>
        </div>
      ))}
    </Part>
  )
}

export function Stack({ thesis }: { thesis: ThesisResponse }) {
  return (
    <Part title="Confirmation stack" sub="each scoring contributor and what it has earned">
      {thesis.confirmation_stack.length === 0 && <span className="tone-dim">No scoring contributors ready.</span>}
      <ul className={styles.stack}>
        {thesis.confirmation_stack.map((c) => (
          <li className={styles.stackItem} key={c.feature_id}>
            <span className={styles.mono}>{c.feature_id}</span>
            <span className={`${styles.mono} ${c.reads === 'LONG' ? 'tone-good' : c.reads === 'SHORT' ? 'tone-bad' : 'tone-dim'}`}>{c.reads} {signed(c.score)}</span>
            <span className={`${styles.pill} ${c.standing === 'scoring' ? styles.pillScoring : styles.pillContext}`}>{c.standing.replace('_', ' ')}</span>
            <span className={`${styles.pill} ${c.earned ? styles.pillEarned : styles.pillNot}`} title={c.earned ? c.earned_by.join(', ') : 'weight not yet earned on the evidence cards'}>{c.earned ? 'earned' : 'not earned'}</span>
          </li>
        ))}
      </ul>
    </Part>
  )
}

export function Conditions({ thesis }: { thesis: ThesisResponse }) {
  return (
    <Part title="No-trade conditions" sub="every reason not to trade, active or clear">
      <ul className={styles.conditions}>
        {thesis.no_trade_conditions.map((c) => (
          <li className={styles.condition} key={c.code}>
            <span className={`${styles.dot} ${c.active ? styles.dotActive : styles.dotClear}`} />
            <span className={styles.code}>{c.code}</span>
            <span className={styles.detail}>{c.detail}</span>
          </li>
        ))}
      </ul>
    </Part>
  )
}

export function Confidence({ thesis }: { thesis: ThesisResponse }) {
  const c = thesis.confidence
  return (
    <Part title="Confidence" sub="evidence coverage, never a win probability">
      <div className={styles.row}><span>Evidence coverage</span><span className={`${styles.mono} metric-main`}>{c.evidence_coverage == null ? '—' : c.evidence_coverage.toFixed(2)}</span></div>
      <div className={styles.row}><span>Skill gate</span><span className={`${styles.mono} ${thesis.skill_gate.gate === 'OPEN' ? 'tone-good' : 'tone-bad'}`}>{thesis.skill_gate.gate ?? '—'}</span></div>
      <div className={styles.row}><span>Observation age</span><span className={styles.mono}>{age(thesis.freshness.observation_age_ms)}</span></div>
      <p className={styles.detail} style={{ margin: 0 }}>{c.meaning}</p>
    </Part>
  )
}
