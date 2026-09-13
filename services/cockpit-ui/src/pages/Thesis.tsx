import { useEffect, useState } from 'react'
import { useTrackedSymbols } from '../api/hooks/useTrackedSymbols'
import { useThesis } from '../api/hooks/useThesis'
import { EditionView } from '../components/thesis/EditionView'
import { Anchors, Conditions, Confidence, Derivatives, Stack, Structure, ThesisText } from './ThesisParts'
import styles from './Thesis.module.css'

/**
 * The Market Thesis page: the latest edition as a trader reads it, and below
 * it the live read for one market, recomputed now, for when the edition is
 * hours old.
 */
export function Thesis() {
  return (
    <div className={styles.page}>
      <EditionView />
      <LiveRead />
    </div>
  )
}

function LiveRead() {
  const { symbols: trackedSymbols } = useTrackedSymbols()
  const [symbol, setSymbol] = useState(trackedSymbols[0] ?? 'BTC-PERP')
  const [open, setOpen] = useState(false)
  useEffect(() => {
    if (trackedSymbols.length && !trackedSymbols.includes(symbol)) setSymbol(trackedSymbols[0])
  }, [trackedSymbols, symbol])
  const { data, isLoading, isError, dataUpdatedAt } = useThesis(open ? symbol : '')

  return (
    <section className="panel">
      <div className="panel-heading">
        <div><h3>Live read</h3><p>one market's thesis recomputed now, independent of the edition</p></div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <select value={symbol} onChange={(e) => setSymbol(e.target.value)} aria-label="Market">
            {trackedSymbols.map((s) => <option key={s}>{s}</option>)}
          </select>
          <button type="button" className={open ? 'chip chip--active' : 'chip'} onClick={() => setOpen(!open)}>
            {open ? 'Hide' : 'Show live read'}
          </button>
        </div>
      </div>
      {open && (
        <div style={{ padding: 16, display: 'grid', gap: 16 }}>
          {isError && <p className="tone-bad">Live thesis unavailable.</p>}
          {isLoading && !data && <p className="tone-dim">Assembling from measured evidence…</p>}
          {data && (
            <>
              <ThesisText thesis={data} updatedAt={dataUpdatedAt} />
              <div className={styles.grid}>
                <Structure thesis={data} />
                <Anchors thesis={data} />
                <Derivatives thesis={data} />
                <Stack thesis={data} />
                <Conditions thesis={data} />
                <Confidence thesis={data} />
              </div>
            </>
          )}
        </div>
      )}
    </section>
  )
}
