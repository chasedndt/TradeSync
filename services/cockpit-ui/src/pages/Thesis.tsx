import { useEffect, useState } from 'react'
import { useTrackedSymbols } from '../api/hooks/useTrackedSymbols'
import { useThesis } from '../api/hooks/useThesis'
import { Anchors, Conditions, Confidence, Derivatives, Stack, Structure, ThesisText } from './ThesisParts'
import { EditionPanel } from '../components/EditionPanel'
import styles from './Thesis.module.css'

/**
 * The Thesis page: the SOP's minimum valid thesis for one symbol, assembled
 * server-side from measured evidence only. Direction is the paper signal's;
 * confidence is coverage; every line names its source and age. The page
 * renders and cannot act.
 */
export function Thesis() {
  const { symbols: trackedSymbols } = useTrackedSymbols()
  const [symbol, setSymbol] = useState(trackedSymbols[0] ?? 'BTC-PERP')
  useEffect(() => {
    if (trackedSymbols.length && !trackedSymbols.includes(symbol)) setSymbol(trackedSymbols[0])
  }, [trackedSymbols, symbol])

  const { data, isLoading, isError, dataUpdatedAt } = useThesis(symbol)

  return (
    <div className={styles.page}>
      <section className={`panel ${styles.hero}`}>
        <div>
          <div className={styles.kicker}>Private daily thesis · paper shadow only</div>
          <h2>What the evidence says about {symbol} right now.</h2>
          <p>
            Chart structure, anchor levels, confirmation stack, invalidation, no-trade conditions and confidence,
            each line from a measured source with its age. Nothing here is drafted by a model and nothing here can act.
          </p>
        </div>
        <div className={styles.controls}>
          <label>
            Symbol
            <select value={symbol} onChange={(e) => setSymbol(e.target.value)}>
              {trackedSymbols.map((s) => <option key={s}>{s}</option>)}
            </select>
          </label>
          {data && (
            <span className={`${styles.verdict} ${data.verdict === 'NO TRADE' ? styles.verdictNo : styles.verdictPaper}`}>
              {data.verdict}
            </span>
          )}
        </div>
      </section>

      <EditionPanel />

      {isError && <section className={`panel ${styles.err}`}>Thesis unavailable. Nothing is inferred.</section>}
      {isLoading && !data && <section className="panel"><p className="tone-dim" style={{ padding: 16 }}>Assembling thesis from measured evidence…</p></section>}

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
  )
}
