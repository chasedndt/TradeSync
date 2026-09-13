import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import type { IChartApi } from 'lightweight-charts'
import { useCandles } from '../api/hooks/useCandles'
import { useOpportunities } from '../api/hooks/useOpportunities'
import { useDepth, useMarketContext } from '../api/hooks/useMarketContext'
import { useCreateDrawing, useDeleteDrawing, useDrawings } from '../api/hooks/useDrawings'
import { PriceChart } from '../components/canvas/PriceChart'
import { AnnotationList } from '../components/canvas/AnnotationList'
import { CanvasToolbar, type PlacingKind } from '../components/canvas/CanvasToolbar'
import { ContextPanes } from '../components/canvas/ContextPanes'
import { DepthLadder } from '../components/canvas/DepthLadder'
import {
  useEvidenceMarkers,
  usePriceLevels,
  useShapes,
} from '../components/canvas/useCanvasLayers'
import { EvidenceTimeline } from '../components/canvas/EvidenceTimeline'
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

  // null = not placing. 'horizontal' takes one click; the two-anchor kinds
  // collect a first anchor and wait for the second.
  const [placing, setPlacing] = useState<PlacingKind | null>(null)
  const [firstAnchor, setFirstAnchor] = useState<{ time_s: number; price: number } | null>(null)
  const [showDepth, setShowDepth] = useState(false)
  const showEvidence = params.get('view') === 'evidence'
  // Held so the context panes can follow this chart's time scale.
  const [chart, setChart] = useState<IChartApi | null>(null)

  const { data, isLoading, isError } = useCandles(symbol, interval, CANDLE_LIMIT)
  const context = useMarketContext(symbol, interval, CANDLE_LIMIT)
  const depth = useDepth(symbol, showDepth)
  const { data: opportunities } = useOpportunities('all', 100)
  const { data: drawings } = useDrawings(symbol, interval)
  const createDrawing = useCreateDrawing()
  const deleteDrawing = useDeleteDrawing()

  const markerMode = params.get('signals') === 'all' ? 'all' : 'changes'
  const markers = useEvidenceMarkers(opportunities, symbol, interval, markerMode)
  const shapes = useShapes(drawings?.drawings)
  const { levels, annotations } = usePriceLevels(
    drawings?.drawings,
    depth.data,
    showDepth,
  )

  const candles = data?.candles ?? []
  const candleTimes = useMemo(() => candles.map((c) => c.time), [candles])
  const last = candles.length ? candles[candles.length - 1] : undefined
  const first = candles.length ? candles[0] : undefined
  const windowChange = first && last ? ((last.close - first.open) / first.open) * 100 : null

  function placePoint(point: { time_s: number; price: number }) {
    if (placing !== 'trendline' && placing !== 'range') return
    if (!firstAnchor) {
      setFirstAnchor(point)
      return
    }
    // Two clicks on the same candle and price would be a degenerate shape; the
    // server refuses it, so stop here with a clearer signal than an error.
    if (firstAnchor.time_s === point.time_s && firstAnchor.price === point.price) {
      setFirstAnchor(null)
      setPlacing(null)
      return
    }
    const kind = placing
    setFirstAnchor(null)
    setPlacing(null)
    createDrawing.mutate({ symbol, interval, kind, points: [firstAnchor, point], label: kind })
  }

  function placeLevel(price: number) {
    if (placing !== 'horizontal') return
    setPlacing(null)
    createDrawing.mutate({
      symbol,
      interval,
      kind: 'horizontal',
      points: [{ time_s: Math.floor(Date.now() / 1000), price: Number(price.toFixed(6)) }],
      label: `level ${price.toFixed(price < 1000 ? 2 : 1)}`,
    })
  }

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
        <CanvasToolbar
          symbols={SYMBOLS}
          intervals={INTERVALS}
          symbol={symbol}
          interval={interval}
          onSymbol={setSymbol}
          onInterval={setInterval}
          placing={placing}
          hasFirstAnchor={firstAnchor !== null}
          onPlacing={(kind) => {
            setFirstAnchor(null)
            setPlacing((current) => (current === kind ? null : kind))
          }}
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
          <>
            <PriceChart
              key={`${symbol}:${interval}`}
              candles={candles}
              markers={showEvidence ? markers : []}
              levels={levels}
              shapes={shapes}
              onChartReady={setChart}
              onPickPrice={placing === 'horizontal' ? placeLevel : undefined}
              onPickPoint={placing === 'trendline' || placing === 'range' ? placePoint : undefined}
            />
            {showEvidence && <ContextPanes
              candleTimes={candleTimes}
              context={context.data}
              isLoading={context.isLoading}
              isError={context.isError}
              syncWith={chart}
            />}
          </>
        )}

        <AnnotationList
          levels={annotations}
          shapes={shapes}
          onRemove={(id) => deleteDrawing.mutate(id)}
          removing={deleteDrawing.isPending}
        />
        {createDrawing.isError && <p role="alert" className="tone-bad">Drawing was not saved. Check the connection and try again.</p>}
        {deleteDrawing.isError && <p role="alert" className="tone-bad">Drawing was not removed. Its stored history is unchanged.</p>}

        <p className="market-footnote" style={{ marginTop: 12 }}>
          Source: Hyperliquid <code>candleSnapshot</code> &nbsp;•&nbsp; markers are
          stored paper opportunities, snapped to the candle open &nbsp;•&nbsp;
          levels are versioned server-side; removing one keeps its history
          &nbsp;•&nbsp; no order can be placed here
        </p>
      </section>

      {showDepth && (
        <section className="panel" style={{ padding: 16, marginTop: 16 }}>
          <div className="panel-heading" style={{ marginBottom: 10 }}>
            <div>
              <h2 style={{ fontSize: 17 }}>Order book</h2>
              <p>
                Resting size right now. Not a series — the book is replaced on
                every poll, so it is shown beside the chart rather than drawn
                across candles it was never present for.
              </p>
            </div>
          </div>
          <DepthLadder
            depth={depth.data}
            isLoading={depth.isLoading}
            isError={depth.isError}
          />
        </section>
      )}

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
    </div>
  )
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: 'good' | 'bad' }) {
  return (
    <div>
      <span className="metric-sub" style={{ display: 'block' }}>
        {label}
      </span>
      <span className={`metric-main ${tone ? `tone-${tone}` : ''}`}>{value}</span>
    </div>
  )
}

function formatPrice(value: number): string {
  return `$${value.toLocaleString('en-US', {
    minimumFractionDigits: value < 1000 ? 2 : 1,
    maximumFractionDigits: value < 1000 ? 2 : 1,
  })}`
}
