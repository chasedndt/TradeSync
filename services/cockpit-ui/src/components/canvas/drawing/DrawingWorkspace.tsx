import { useCallback, useState, type ReactNode } from 'react'
import type { IChartApi } from 'lightweight-charts'
import type { Candle } from '../../../api/types'
import { AnnotationList } from '../AnnotationList'
import type { ChartHandles, EvidenceMarker, PriceLevel } from '../chartTypes'
import { PriceChart } from '../PriceChart'
import { StyleBar } from './StyleBar'
import { TextInput } from './TextInput'
import { ToolRail } from './ToolRail'
import { useDrawingController } from './useDrawingController'
import styles from './DrawingWorkspace.module.css'

interface Props {
  symbol: string
  interval: string
  candles: Candle[]
  markers: EvidenceMarker[]
  /** Venue-derived price lines, such as resting walls. */
  levels: PriceLevel[]
  /** Handed the chart so panes below can follow its time scale; null on unmount. */
  onChartReady: (chart: IChartApi | null) => void
  /** Panes that follow the chart, aligned under its plot area rather than under the rail. */
  children?: ReactNode
}

/**
 * The price chart with the drawing tool rail beside it and the operator's
 * drawings listed below. Drawings are annotation only: nothing drawn here can
 * score, approve or place anything.
 */
export function DrawingWorkspace({ symbol, interval, candles, markers, levels, onChartReady, children }: Props) {
  const [handles, setHandles] = useState<ChartHandles | null>(null)
  const onReady = useCallback(
    (next: ChartHandles | null) => {
      setHandles(next)
      onChartReady(next?.chart ?? null)
    },
    [onChartReady],
  )
  const drawing = useDrawingController({ handles, symbol, interval, candles })

  return (
    <>
      <div className={styles.workspace}>
        <ToolRail
          tool={drawing.tool}
          onTool={drawing.chooseTool}
          hidden={drawing.hidden}
          onToggleHidden={drawing.toggleHidden}
          locked={drawing.locked}
          onToggleLocked={drawing.toggleLocked}
          count={drawing.shapes.length}
          symbol={symbol}
          onClearAll={drawing.clearAll}
        />
        <div className={styles.column}>
          <div className={styles.chart}>
            <PriceChart key={`${symbol}:${interval}`} candles={candles} markers={markers} levels={levels} onReady={onReady} />
            {drawing.selected && !drawing.hidden && (
              <StyleBar
                shape={drawing.selected}
                interval={interval}
                locked={drawing.locked}
                onStyle={drawing.restyle}
                onDelete={drawing.deleteSelected}
              />
            )}
            {drawing.textDraft && (
              <TextInput
                at={drawing.textDraft.at}
                colour={drawing.style.colour}
                onSubmit={drawing.submitText}
                onCancel={drawing.cancelText}
              />
            )}
          </div>
          {children}
        </div>
      </div>

      <AnnotationList
        shapes={drawing.shapes}
        interval={interval}
        selectedId={drawing.selected?.id ?? null}
        locked={drawing.locked}
        removing={drawing.removing}
        onSelect={drawing.select}
        onRemove={drawing.removeDrawing}
      />
      {drawing.saveFailed && <p role="alert" className="tone-bad">Drawing was not saved. Check the connection and try again.</p>}
      {drawing.removeFailed && <p role="alert" className="tone-bad">Drawing was not removed. Its stored history is unchanged.</p>}
    </>
  )
}
