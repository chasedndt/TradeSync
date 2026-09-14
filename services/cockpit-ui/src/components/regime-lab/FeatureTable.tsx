import { useEffect, useMemo, useState } from 'react'
import type { UseQueryResult } from '@tanstack/react-query'
import type { EvidenceCard, EvidenceCardsReading } from '../../api/outcomeEvidenceTypes'
import type { RegimeLabFeatureResult, RegimeLabOverview } from '../../api/regimeLabTypes'
import { FeatureRow } from './FeatureRow'
import type { CardsState } from './featureReason'
import { blockLabel, percent, signed } from './format'
import styles from './FeatureTable.module.css'

const COLUMNS = ['Feature', 'Value', 'Age', 'History', 'z', 'Score', 'Reason', 'Evidence card', 'Entries']

interface Props {
  symbol: string
  overview: UseQueryResult<RegimeLabOverview, Error>
  cards: UseQueryResult<EvidenceCardsReading, Error>
}

interface BlockGroup {
  block: string
  summary: string
  features: RegimeLabFeatureResult[]
}

/**
 * Every catalog feature for one market, grouped by rulebook block: its reading,
 * age, history, z-score, score, why it is or is not scoring, and what its
 * evidence card says. A row opens its seven-day chart; #feature-<id> opens one.
 */
export function FeatureTable({ symbol, overview, cards }: Props) {
  const data = overview.data
  const [open, setOpen] = useState<Set<string>>(() => {
    const target = hashTarget()
    return new Set(target ? [target] : [])
  })
  const [scrollTo, setScrollTo] = useState<string | null>(() => hashTarget())
  const groups = useMemo(() => (data ? groupByBlock(data) : []), [data])
  const cardById = useMemo(
    () => new Map<string, EvidenceCard>(cards.data?.status === 'ready' ? cards.data.cards.map((card) => [card.feature_id, card]) : []),
    [cards.data],
  )
  const cardsState: CardsState = cards.data
    ? (cards.data.status === 'computing' ? 'computing' : 'ready')
    : cards.isError ? 'error' : 'loading'

  useEffect(() => {
    const onHash = () => {
      const target = hashTarget()
      if (!target) return
      setOpen((previous) => new Set(previous).add(target))
      setScrollTo(target)
    }
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  // Scroll to a linked feature once its row exists, not again on every refresh.
  useEffect(() => {
    if (!scrollTo || !data) return
    document.getElementById(`feature-${scrollTo}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    setScrollTo(null)
  }, [scrollTo, data])

  const toggle = (id: string) =>
    setOpen((previous) => {
      const next = new Set(previous)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  return (
    <section className={`panel ${styles.panel}`} aria-labelledby="feature-evidence-title">
      <div className={`panel-heading ${styles.heading}`}>
        <div>
          <h3 id="feature-evidence-title">Feature evidence</h3>
          <p>{symbol}{data ? ` · catalog v${data.catalog.version} · baseline rulebook v${data.baseline.version}` : ''} · a row opens its seven-day chart</p>
        </div>
        {data && (
          <div className={styles.chartControls}>
            <button type="button" className="chip" onClick={() => setOpen(new Set(data.feature_results.map((feature) => feature.feature_id)))}>Show every chart</button>
            {open.size > 0 && <button type="button" className="chip" onClick={() => setOpen(new Set())}>Hide charts</button>}
          </div>
        )}
      </div>
      {overview.isLoading && <p className={styles.state}>Reading feature evidence for {symbol}…</p>}
      {!data && overview.error && <p className={`${styles.state} tone-bad`}>Feature evidence unavailable: {overview.error.message}</p>}
      {data && (
        <div className={styles.scroll}>
          <table className={styles.table}>
            <thead>
              <tr>{COLUMNS.map((column) => <th key={column} scope="col">{column}</th>)}</tr>
            </thead>
            {groups.map((group) => (
              <tbody key={group.block}>
                <tr className={styles.blockRow}>
                  <th colSpan={COLUMNS.length} scope="colgroup">
                    <span className={styles.blockName}>{blockLabel(group.block)}</span>
                    <span className={styles.blockMeta}>{group.summary}</span>
                  </th>
                </tr>
                {group.features.map((feature) => (
                  <FeatureRow
                    key={feature.feature_id}
                    feature={feature}
                    symbol={symbol}
                    open={open.has(feature.feature_id)}
                    onToggle={() => toggle(feature.feature_id)}
                    card={cardById.get(feature.feature_id)}
                    cardsState={cardsState}
                    columns={COLUMNS.length}
                  />
                ))}
              </tbody>
            ))}
          </table>
        </div>
      )}
    </section>
  )
}

function hashTarget(): string | null {
  const hash = typeof window === 'undefined' ? '' : window.location.hash
  return hash.startsWith('#feature-') ? decodeURIComponent(hash.slice('#feature-'.length)) : null
}

/** Blocks in rulebook order, then any block only display features belong to. */
function groupByBlock(data: RegimeLabOverview): BlockGroup[] {
  const order = Object.keys(data.baseline.weights)
  for (const feature of data.feature_results) {
    if (!order.includes(feature.block)) order.push(feature.block)
  }
  return order
    .map((block) => {
      const evidence = data.block_evidence[block]
      const weight = data.baseline.weights[block]
      const parts = [weight == null ? 'no rulebook weight' : `weight ${weight.toFixed(2)}`]
      if (evidence) {
        parts.push(
          evidence.admitted_feature_ids.length === 0
            ? 'no admitted features'
            : `${evidence.ready_features.length} of ${evidence.admitted_feature_ids.length} admitted features scoring`,
          `block score ${signed(evidence.score, 3)}`,
          `quality ${percent(evidence.quality, 0)}`,
        )
      }
      return { block, summary: parts.join(' · '), features: data.feature_results.filter((feature) => feature.block === block) }
    })
    .filter((group) => group.features.length > 0)
}
