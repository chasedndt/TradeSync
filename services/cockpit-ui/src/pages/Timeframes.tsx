import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useHorizonChart, useHorizonPage } from '../api/hooks/useHorizons'
import { useTrackedSymbols } from '../api/hooks/useTrackedSymbols'
import type { HorizonKey } from '../api/horizonTypes'
import { FeatureCard } from '../components/horizons/FeatureCard'
import { HorizonBands } from '../components/horizons/HorizonBands'
import { LinkedText, type LinkTarget } from '../components/horizons/LinkedText'
import { ReadingPanel } from '../components/horizons/ReadingPanel'
import { IntradayHorizons } from '../components/horizons/IntradayHorizons'
import { price, since } from '../components/ledger/format'
import styles from './Timeframes.module.css'

const HORIZON_KEYS: HorizonKey[] = ['3d', '1w', '2w', '1m', '3m', '6m']

/**
 * Timeframes: what the record says for the lower (3 days, 1 week), medium
 * (2 weeks, 1 month) and higher (3 and 6 months) time frames, from Hyperliquid
 * daily candles. Each horizon gives the trend and momentum state and what
 * followed days like today; each feature has a chart drawn the way it reads,
 * with the record's cone forward. Feature names anywhere on the page, Hermes's
 * reading included, link to their charts.
 */
export function Timeframes() {
  const [params, setParams] = useSearchParams()
  const { symbols } = useTrackedSymbols()
  const symbol = params.get('symbol') ?? symbols[0] ?? 'BTC-PERP'
  const requested = params.get('horizon') as HorizonKey | null
  const horizon: HorizonKey = requested && HORIZON_KEYS.includes(requested) ? requested : '1m'
  const page = useHorizonPage(symbol)
  const chart = useHorizonChart(symbol, horizon)
  const [highlight, setHighlight] = useState<string | null>(null)

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params)
    next.set(key, value)
    setParams(next, { replace: true })
  }
  const targets: LinkTarget[] = useMemo(() => (page.data?.features ?? []).map((f) => ({ label: f.label, key: f.key })), [page.data])
  const pickFeature = (key: string, from?: HorizonKey) => {
    if (from && from !== horizon) setParam('horizon', from)
    setHighlight(key)
  }

  useEffect(() => {
    if (!highlight) return
    const card = () => document.getElementById(`feature-${highlight}`)
    const inView = (el: HTMLElement) => { const r = el.getBoundingClientRect(); return r.top < window.innerHeight && r.bottom > 0 }
    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    const scroll = window.setTimeout(() => card()?.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'center' }), 80)
    // Smooth scrolling stalls where the page is not painting (a background tab); jump if it has not arrived.
    const fallback = window.setTimeout(() => { const el = card(); if (el && !inView(el)) el.scrollIntoView({ behavior: 'auto', block: 'center' }) }, 900)
    const clear = window.setTimeout(() => setHighlight(null), 2400)
    return () => { window.clearTimeout(scroll); window.clearTimeout(fallback); window.clearTimeout(clear) }
  }, [highlight, horizon])

  const data = page.data
  const outlook = data?.outlook
  const selected = outlook?.horizons?.find((h) => h.key === horizon)
  const evaluation = data?.evaluation[horizon]
  const chartForHorizon = chart.data?.horizon === horizon ? chart.data : undefined

  return (
    <div className={styles.page}>
      <section className={`panel ${styles.hero}`}>
        <div>
          <div className={styles.kicker}>Lower · medium · higher time frame · Hyperliquid daily candles · a record, not a forecast</div>
          <h2>Timeframes</h2>
          <p>
            For each horizon from three days to six months: where the trend and momentum stand, what followed past days in the same state,
            the range an ordinary move spans, and what each feature reads. Nothing here is weighted, because no feature has measured skill
            at these horizons. Click a feature name to see its chart.
          </p>
        </div>
        <div className={styles.side}>
          <div className={styles.chips} role="group" aria-label="Market">
            {symbols.map((s) => (
              <button key={s} type="button" className={s === symbol ? 'chip chip--active' : 'chip'} aria-pressed={s === symbol} onClick={() => setParam('symbol', s)}>
                {s.replace('-PERP', '')}
              </button>
            ))}
          </div>
          <span className="metric-sub">
            {outlook?.last_close != null ? `last close ${price(outlook.last_close)}` : ''}{data ? ` · measured ${since(data.computed_at)}` : ''}
          </span>
        </div>
      </section>

      <IntradayHorizons symbol={symbol} />
      {page.isLoading && <section className="panel"><p className={styles.message}>Measuring {symbol} across six daily-history horizons…</p></section>}
      {page.isError && <section className="panel"><p className={styles.error}>Timeframes unavailable: {(page.error as Error).message}</p></section>}
      {data && !outlook?.available && <section className="panel"><p className={styles.message}>{outlook?.reason}</p></section>}

      {data && outlook?.available && (
        <>
          <HorizonBands page={data} selected={horizon} targets={targets} onSelect={(k) => setParam('horizon', k)} onPickFeature={pickFeature} />
          <ReadingPanel symbol={symbol} reading={data.reading} targets={targets} onPickFeature={(k) => pickFeature(k)} />

          <section className={`panel ${styles.featuresHead}`} aria-labelledby="features-title">
            <div className={styles.featuresTop}>
              <h3 id="features-title">Features over {selected?.label ?? horizon}</h3>
              <div className={styles.chips} role="group" aria-label="Horizon">
                {data.horizons.map((h) => (
                  <button key={h.key} type="button" className={h.key === horizon ? 'chip chip--active' : 'chip'} aria-pressed={h.key === horizon} onClick={() => setParam('horizon', h.key)}>
                    {h.label}
                  </button>
                ))}
              </div>
            </div>
            {evaluation && <p className={styles.summary}><LinkedText text={evaluation.summary} targets={targets} onPick={(k) => pickFeature(k)} /></p>}
          </section>

          <div className={styles.grid}>
            {(evaluation?.features ?? []).map((feature) => (
              <FeatureCard
                key={`${horizon}-${feature.key}`}
                feature={feature}
                horizonLabel={selected?.label ?? horizon}
                chart={chartForHorizon}
                chartState={chart.isError ? 'error' : chartForHorizon ? 'ready' : 'loading'}
                highlighted={highlight === feature.key}
              />
            ))}
          </div>
          <p className={styles.note}>{data.note} {data.history_note} {chartForHorizon?.projection.note ?? ''}</p>
        </>
      )}
    </div>
  )
}
