import { EvidenceTimeline } from './EvidenceTimeline'

/** Recorded paper calls compared at fixed horizons, below the chart. */
export function EvidencePanel({ symbol }: { symbol: string }) {
  return (
    <section className="panel" style={{ padding: 16, marginTop: 16 }}>
      <div className="panel-heading" style={{ marginBottom: 10 }}>
        <div>
          <h2 style={{ fontSize: 17 }}>Paper outcomes & evidence</h2>
          <p>
            Compare each recorded call at fixed horizons. Returns are hypothetical,
            before fees, funding and slippage — not realized account P&amp;L.
          </p>
        </div>
      </div>
      <EvidenceTimeline symbol={symbol} />
    </section>
  )
}
