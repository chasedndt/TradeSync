import type { SetURLSearchParams } from 'react-router-dom'

interface Props {
  params: URLSearchParams
  setParams: SetURLSearchParams
  showEvidence: boolean
  markerMode: 'changes' | 'all'
}

/** Chart or research-signal view, and which calls mark the chart. Both live in the URL. */
export function CanvasViewChips({ params, setParams, showEvidence, markerMode }: Props) {
  return (
    <div role="group" aria-label="Chart view" style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 16 }}>
      {(['chart', 'evidence'] as const).map((view) => (
        <button key={view} type="button" className={(showEvidence === (view === 'evidence')) ? 'chip chip--active' : 'chip'}
          aria-pressed={showEvidence === (view === 'evidence')}
          onClick={() => { const next = new URLSearchParams(params); next.set('view', view); setParams(next, { replace: true }) }}>
          {view === 'chart' ? 'Chart & drawings' : 'Research signals'}
        </button>
      ))}
      {showEvidence && (['changes', 'all'] as const).map((mode) => (
        <button key={mode} type="button" className={markerMode === mode ? 'chip chip--active' : 'chip'} aria-pressed={markerMode === mode}
          onClick={() => { const next = new URLSearchParams(params); next.set('signals', mode); setParams(next, { replace: true }) }}
          title={mode === 'changes' ? 'Only mark where the paper read changed side' : 'Also mark every candle that carried a call, as small dots'}>
          {mode === 'changes' ? 'Side changes' : 'Every call'}
        </button>
      ))}
      <span className="metric-sub">Drawings stay visible in both views. Research signals are not executed positions.</span>
    </div>
  )
}
