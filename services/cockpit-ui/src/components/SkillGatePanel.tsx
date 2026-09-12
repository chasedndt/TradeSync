import { useSkillGate } from '../api/hooks/useSkillGate'
import type { SkillGateCell } from '../api/types'

/**
 * Three verdicts per horizon and regime, never collapsed into one.
 *
 * "Detectable" says the sample can tell the result apart from zero — in
 * either direction. "Positive skill" says it beat a biased guesser after
 * adjusting for how many cells were tested. "Economic edge" says it still
 * paid after the stated costs. A cell can be detectably *bad*. The gate opens
 * only on economic edge, and even then only with explicit operator approval.
 */
export function SkillGatePanel({ symbol }: { symbol?: string }) {
  const { data, isLoading, isError } = useSkillGate(symbol)

  if (isError) return <section className="panel lab-section"><p className="tone-bad">Skill gate unavailable. Nothing is inferred.</p></section>
  if (isLoading || !data) return <section className="panel lab-section"><p className="tone-dim">Measuring skill gate… (block bootstrap over every cell)</p></section>

  const v = data.verdict
  return (
    <section className="panel lab-section" aria-labelledby="skill-gate-title">
      <div className="panel-heading">
        <div>
          <h2 id="skill-gate-title">Skill gate</h2>
          <p>Entry-time regimes · counted independence · Holm-adjusted across {data.cells_assessed_together} cells{symbol ? ` · ${symbol}` : ' · all symbols'}</p>
        </div>
        <span className={v.gate === 'OPEN' ? 'tone-good' : 'tone-bad'}>{v.gate}</span>
      </div>

      <div style={{ display: 'flex', gap: 22, flexWrap: 'wrap', padding: '0 16px 10px' }}>
        <Verdict label="Detectable anywhere" value={v.any_detectable} />
        <Verdict label="Positive skill anywhere" value={v.any_positive_skill} />
        <Verdict label="Economic edge anywhere" value={v.any_economic_edge} />
        <span className="metric-sub" style={{ alignSelf: 'end' }}>
          costs {data.costs.total_pct.toFixed(3)}% round trip · {data.entry_regimes_pending > 0 ? `${data.entry_regimes_pending} opportunities not yet regime-labelled` : 'all opportunities regime-labelled'}
        </span>
      </div>

      <div style={{ overflowX: 'auto', padding: '0 16px 12px' }}>
        <table className="market-table" style={{ fontSize: 12 }}>
          <thead>
            <tr><th>Horizon</th><th>Regime</th><th>n</th><th>independent</th><th>skill</th><th>z</th><th>net %</th><th>hold-out</th><th>detectable</th><th>positive</th><th>edge</th></tr>
          </thead>
          <tbody>
            {data.cells.map((c) => <CellRow key={c.label} c={c} />)}
          </tbody>
        </table>
      </div>
      <p className="market-footnote" style={{ padding: '0 16px 14px' }}>{data.note} Costs: {data.costs.source}.</p>
    </section>
  )
}

function Verdict({ label, value }: { label: string; value: boolean }) {
  return (
    <div>
      <span className="metric-sub" style={{ display: 'block' }}>{label}</span>
      <span className={`metric-main ${value ? 'tone-good' : 'tone-dim'}`}>{value ? 'YES' : 'no'}</span>
    </div>
  )
}

function CellRow({ c }: { c: SkillGateCell }) {
  const pts = (x: number | null) => (x == null ? '—' : `${(x * 100) >= 0 ? '+' : ''}${(x * 100).toFixed(1)} pts`)
  return (
    <tr>
      <td>{c.horizon_minutes}m</td>
      <td>{c.regime}</td>
      <td>{c.measured}</td>
      <td title="per symbol / pooled">{c.independent_per_symbol} / <strong>{c.independent_pooled}</strong></td>
      <td className={c.skill != null && c.skill > 0 ? 'tone-good' : 'tone-bad'}>{pts(c.skill)}</td>
      <td>{c.z == null ? '—' : c.z.toFixed(2)}</td>
      <td>{c.mean_net_return_pct == null ? '—' : `${c.mean_net_return_pct.toFixed(3)}%`}</td>
      <td title={`in-sample ${pts(c.in_sample_skill)} · hold-out ${pts(c.holdout_skill)} (n=${c.holdout_measured})`}>{pts(c.holdout_skill)}</td>
      <td className={c.detectable ? 'tone-warn' : 'tone-dim'}>{c.detectable ? 'yes' : 'no'}</td>
      <td className={c.positive_skill ? 'tone-good' : 'tone-dim'}>{c.positive_skill ? 'YES' : 'no'}</td>
      <td className={c.economic_edge ? 'tone-good' : 'tone-dim'}>{c.economic_edge == null ? 'uncosted' : c.economic_edge ? 'YES' : 'no'}</td>
    </tr>
  )
}
