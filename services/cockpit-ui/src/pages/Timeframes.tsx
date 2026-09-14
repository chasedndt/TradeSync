import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useHorizonChart, useHorizonPage } from '../api/hooks/useHorizons'
import { useTrackedSymbols } from '../api/hooks/useTrackedSymbols'
import { HORIZON_KEYS, partOf, type HorizonKey } from '../api/horizonTypes'
import { BandReading } from '../components/horizons/BandReading'
import { EvidenceTable } from '../components/horizons/EvidenceTable'
import { HorizonDetail } from '../components/horizons/HorizonDetail'
import { HorizonStrip } from '../components/horizons/HorizonStrip'
import type { LinkTarget } from '../components/horizons/LinkedText'
import { TimeframesHeader } from '../components/horizons/TimeframesHeader'
import { HorizonChart } from '../components/horizons/chart/HorizonChart'
import styles from './TimeframesPage.module.css'

const DEFAULT_OVERLAYS = ['trend', 'volatility', 'rsi']

/**
 * Timeframes: every horizon from one hour to six months at a glance, then the
 * selected horizon in words, Hermes's reading of its time frame with the exact
 * time it was read, one large chart, and every feature's evidence with the
 * weight it earned out of sample. Feature names anywhere on the page put that
 * feature on the chart and point to its row.
 */
export function Timeframes() {
  const [params, setParams] = useSearchParams()
  const { symbols } = useTrackedSymbols()
  const symbol = params.get('symbol') ?? symbols[0] ?? 'BTC-PERP'
  const requested = params.get('horizon') as HorizonKey | null
  const horizon: HorizonKey = requested && HORIZON_KEYS.includes(requested) ? requested : '4h'
  const page = useHorizonPage(symbol)
  const data = page.data
  const meta = data?.horizons.find((h) => h.key === horizon)
  const measuredAt = meta ? data?.computed_at[partOf(meta.interval)] : undefined
  const chart = useHorizonChart(symbol, horizon, measuredAt)
  const [active, setActive] = useState<Set<string>>(() => new Set(DEFAULT_OVERLAYS))
  const [highlight, setHighlight] = useState<string | null>(null)

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params)
    next.set(key, value)
    setParams(next, { replace: true })
  }
  const toggle = useCallback((key: string) => setActive((prev) => {
    const next = new Set(prev)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    return next
  }), [])
  const labels = useMemo(() => Object.fromEntries((data?.features ?? []).map((f) => [f.key, f.label])), [data])
  const targets: LinkTarget[] = useMemo(() => (data?.features ?? []).map((f) => ({ label: f.label, key: f.key })), [data])
  const pick = (key: string) => {
    setActive((prev) => new Set(prev).add(key))
    setHighlight(key)
  }

  useEffect(() => {
    if (!highlight) return
    document.getElementById(`feature-${highlight}`)?.scrollIntoView({ block: 'center' })
    const clear = window.setTimeout(() => setHighlight(null), 2400)
    return () => window.clearTimeout(clear)
  }, [highlight])

  const read = data?.outlook.horizons.find((h) => h.key === horizon)
  const chartData = chart.data?.horizon === horizon ? chart.data : undefined
  const chartStatus = chart.isError ? `Chart unavailable: ${(chart.error as Error).message}` : !measuredAt ? 'Measuring this horizon…' : null

  return (
    <div className={styles.page}>
      <TimeframesHeader symbols={symbols} symbol={symbol} onSymbol={(s) => setParam('symbol', s)} page={data} />
      {page.isLoading && <section className="panel"><p className={styles.message}>Measuring {symbol} from one hour to six months…</p></section>}
      {page.isError && <section className="panel"><p className={styles.error}>Timeframes unavailable: {(page.error as Error).message}</p></section>}
      {data && (
        <>
          <HorizonStrip page={data} selected={horizon} onSelect={(key) => setParam('horizon', key)} />
          {read && (
            <div className={styles.split}>
              <HorizonDetail read={read} evaluation={data.evaluation[horizon]} targets={targets} onPick={pick} />
              <BandReading symbol={symbol} band={read.band} label={data.bands[read.band]} reading={data.readings[read.band]}
                measuredAt={measuredAt} targets={targets} onPick={pick} />
            </div>
          )}
          <HorizonChart payload={chartData} status={chartStatus} horizonLabel={read?.label ?? horizon} labels={labels} active={active} onToggle={toggle} />
          <EvidenceTable evaluation={data.evaluation[horizon]} horizonLabel={read?.label ?? horizon} active={active} onToggle={toggle} highlight={highlight} />
          <p className={styles.note}>{data.note} {data.history_note}</p>
        </>
      )}
    </div>
  )
}
