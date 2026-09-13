import type { ThesisResponse } from '../../api/types'
import { formatPrice } from '../home/format'
import styles from './Thesis.module.css'

function derivative(d: ThesisResponse['derivatives'][number]): string {
  if (d.value == null) return '—'
  const u = d.unit ?? ''
  if (u === 'basis_points') return `${d.value >= 0 ? '+' : ''}${d.value.toFixed(1)} bps`
  if (u.startsWith('percent')) return `${d.value >= 0 ? '+' : ''}${d.value.toFixed(2)}%`
  if (u.startsWith('decimal_rate') || u.startsWith('rate_per')) return `${(d.value * 100).toFixed(4)}%`
  if (u.startsWith('decimal_APR')) return `${(d.value * 100).toFixed(1)}% APR`
  if (u === 'USD_delta') return `${d.value >= 0 ? '+' : ''}${Intl.NumberFormat('en-US', { notation: 'compact' }).format(d.value)}`
  return d.value.toFixed(2)
}

function SymbolCard({ t }: { t: ThesisResponse }) {
  const s = t.structure
  const a = t.anchors
  const cov = t.confidence.evidence_coverage
  const active = t.no_trade_conditions.filter((c) => c.active)
  const tone = s.direction === 'LONG' ? 'tone-good' : s.direction === 'SHORT' ? 'tone-bad' : 'tone-dim'
  return (
    <article className={styles.symbol} aria-label={t.symbol}>
      <header className={styles.symbolHead}>
        <strong>{t.symbol.replace('-PERP', '')}</strong>
        <span className={`pill ${t.verdict === 'NO TRADE' ? 'pill--bad' : 'pill--warn'}`}>{t.verdict}</span>
        <span className={`${styles.dir} ${tone}`}>{s.direction === 'NONE' ? 'no read' : s.direction}</span>
      </header>
      <div className={styles.kv}>
        <span>regime</span>
        <b>{s.entry_regime}{s.trailing_return_pct != null ? ` (${s.trailing_return_pct >= 0 ? '+' : ''}${s.trailing_return_pct.toFixed(2)}%)` : ''}</b>
        <span>last</span><b>{formatPrice(a.last_close)}</b>
        <span>24h range</span><b>{formatPrice(a.low_24h)} – {formatPrice(a.high_24h)}</b>
        <span>1h range</span><b>{formatPrice(a.low_1h)} – {formatPrice(a.high_1h)}</b>
        <span>invalidation</span><b className="tone-warn">{formatPrice(t.invalidation.level)}</b>
      </div>
      <div className={styles.coverage} title="evidence coverage"><span style={{ width: `${Math.round((cov ?? 0) * 100)}%` }} /></div>
      <span className="metric-sub">
        coverage {cov != null ? cov.toFixed(2) : '—'} · score {s.directional_score != null ? `${s.directional_score >= 0 ? '+' : ''}${s.directional_score.toFixed(2)}` : '—'}
      </span>
      <div className={styles.derivs}>
        {t.derivatives.filter((d) => d.value != null).slice(0, 5).map((d) => (
          <span key={d.feature_id}>{d.label} <b>{derivative(d)}</b></span>
        ))}
      </div>
      {active.length > 0 && (
        <div className={styles.conds}>{active.map((c) => <span key={c.code} title={c.detail}>{c.code.replace(/_/g, ' ')}</span>)}</div>
      )}
    </article>
  )
}

/** Every market's thesis as a card: verdict, read, levels, coverage, context and what is blocking a trade. */
export function SymbolGrid({ theses, order }: { theses: Record<string, ThesisResponse>; order: string[] }) {
  return (
    <div className={styles.symbols}>
      {order.filter((s) => theses[s]).map((s) => <SymbolCard key={s} t={theses[s]} />)}
    </div>
  )
}
