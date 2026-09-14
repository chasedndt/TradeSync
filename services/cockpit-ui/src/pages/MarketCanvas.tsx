import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import type { IChartApi } from 'lightweight-charts'
import { useCandles } from '../api/hooks/useCandles'
import { useOpportunities } from '../api/hooks/useOpportunities'
import { useDepth, useMarketContext } from '../api/hooks/useMarketContext'
import { CanvasToolbar } from '../components/canvas/CanvasToolbar'
import { CanvasViewChips } from '../components/canvas/CanvasViewChips'
import { Stat } from '../components/canvas/CanvasStat'
import { ContextPanes } from '../components/canvas/ContextPanes'
import { DrawingWorkspace } from '../components/canvas/drawing/DrawingWorkspace'
import { EvidencePanel } from '../components/canvas/EvidencePanel'
import { formatPrice } from '../components/canvas/format'
import { OrderBookPanel } from '../components/canvas/OrderBookPanel'
import { useDepthWalls, useEvidenceMarkers } from '../components/canvas/useCanvasLayers'
import { useTrackedSymbols } from '../api/hooks/useTrackedSymbols'

const INTERVALS = ['1m', '5m', '15m', '1h', '4h', '1d']
const CANDLE_LIMIT = 300

/**
 * Market Canvas — Hyperliquid price with the paper evidence recorded against
 * it, the funding and open interest underneath, and the current book beside it.
 *
 * Every marker corresponds to a stored opportunity row and every series names
 * its source, so nothing on this page is illustrative. Display only: no order
 * can be placed here and nothing drawn here reaches the feature catalog.
 */
export function MarketCanvas() {
  // Symbol and interval live in the URL so a chart can be linked to directly
  // from Mission Control and shared or reopened as a specific view.
  const [params, setParams] = useSearchParams()
  const { symbols: SYMBOLS } = useTrackedSymbols()
  const requested = params.get('symbol')
  const symbol = requested && SYMBOLS.includes(requested) ? requested : SYMBOLS[0]
  const requestedInterval = params.get('interval')
  const interval =
    requestedInterval && INTERVALS.includes(requestedInterval) ? requestedInterval : '15m'

  const setSymbol = (next: string) => {
    params.set('symbol', next)
    setParams(params, { replace: true })
  }
  const setInterval = (next: string) => {
    params.set('interval', next)
    setParams(params, { replace: true })
  }

  const [showDepth, setShowDepth] = useState(false)
  const showEvidence = params.get('view') === 'evidence'
  // Held so the context panes can follow this chart's time scale.
  const [chart, setChart] = useState<IChartApi | null>(null)

  const { data, isLoading, isError } = useCandles(symbol, interval, CANDLE_LIMIT)
  const context = useMarketContext(symbol, interval, CANDLE_LIMIT)
  const depth = useDepth(symbol, showDepth)
  const { data: opportunities } = useOpportunities('all', 100)

  const markerMode = params.get('signals') === 'all' ? 'all' : 'changes'
  const markers = useEvidenceMarkers(opportunities, symbol, interval, markerMode)
  const walls = useDepthWalls(depth.data, showDepth)

  const candles = data?.candles ?? []
  const candleTimes = useMemo(() => candles.map((c) => c.time), [candles])
  const last = candles.length ? candles[candles.length - 1] : undefined
  const first = candles.length ? candles[0] : undefined
  const windowChange = first && last ? ((last.close - first.open) / first.open) * 100 : null

  return (
    <div className="page">
      <header className="panel-heading" style={{ marginBottom: 16 }}>
        <div>
          <h2>Market Canvas</h2>
          <p>
            Hyperliquid candles with recorded paper evidence, funding and open
            interest. Display only — nothing here scores.
          </p>
        </div>
      </header>

      <section className="panel" style={{ padding: 16 }}>
        <CanvasViewChips
          params={params}
          setParams={setParams}
          showEvidence={showEvidence}
          markerMode={markerMode}
        />
        <CanvasToolbar
          symbols={SYMBOLS}
          intervals={INTERVALS}
          symbol={symbol}
          interval={interval}
          onSymbol={setSymbol}
          onInterval={setInterval}
          showDepth={showDepth}
          onToggleDepth={() => setShowDepth((v) => !v)}
        >
          <Stat label="Last" value={last ? formatPrice(last.close) : '—'} />
          <Stat
            label={`Window (${candles.length})`}
            value={
              windowChange == null
                ? '—'
                : `${windowChange >= 0 ? '+' : ''}${windowChange.toFixed(2)}%`
            }
            tone={windowChange == null ? undefined : windowChange >= 0 ? 'good' : 'bad'}
          />
          <Stat label={markerMode === 'changes' ? 'Side changes' : 'Marked candles'} value={String(markers.length)} />
        </CanvasToolbar>

        {isError ? (
          <p className="tone-bad">
            Candles unavailable. Hyperliquid or market-data did not answer; no
            substitute series is drawn.
          </p>
        ) : isLoading ? (
          <p className="tone-dim">Loading candles…</p>
        ) : candles.length === 0 ? (
          <p className="tone-dim">
            The venue returned no candles for this window. Nothing is interpolated.
          </p>
        ) : (
          <DrawingWorkspace
            symbol={symbol}
            interval={interval}
            candles={candles}
            markers={showEvidence ? markers : []}
            levels={walls}
            onChartReady={setChart}
          >
            {showEvidence && <ContextPanes
              candleTimes={candleTimes}
              context={context.data}
              isLoading={context.isLoading}
              isError={context.isError}
              syncWith={chart}
            />}
          </DrawingWorkspace>
        )}

        <p className="market-footnote" style={{ marginTop: 12 }}>
          Source: Hyperliquid <code>candleSnapshot</code> &nbsp;•&nbsp; markers are
          stored paper opportunities, snapped to the candle open &nbsp;•&nbsp;
          drawings are versioned server-side and shown on every interval; removing
          one keeps its history &nbsp;•&nbsp; no order can be placed here
        </p>
      </section>

      {showDepth && (
        <OrderBookPanel
          depth={depth.data}
          isLoading={depth.isLoading}
          isError={depth.isError}
        />
      )}

      <EvidencePanel symbol={symbol} />
    </div>
  )
}
