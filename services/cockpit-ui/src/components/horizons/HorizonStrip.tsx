import type { BandKey, CombinedReading, HorizonKey, HorizonPage, HorizonRead } from '../../api/horizonTypes'
import { partOf } from '../../api/horizonTypes'
import { AGREEMENT, COMBINED_LABEL, signedPct } from './timeframeText'
import styles from './HorizonStrip.module.css'

interface Props {
  page: HorizonPage
  selected: HorizonKey
  onSelect: (key: HorizonKey) => void
}

/** Every horizon at a glance, grouped by time frame: the weighted lean, where price sits against its trend, and the move. */
export function HorizonStrip({ page, selected, onSelect }: Props) {
  const reads = new Map(page.outlook.horizons.map((r) => [r.key, r]))
  return (
    <div className={styles.strip}>
      {(Object.keys(page.bands) as BandKey[]).map((band) => {
        const summary = page.outlook.bands.find((b) => b.band === band)
        return (
          <section key={band} className={`panel ${styles.band}`} aria-label={page.bands[band]}>
            <header className={styles.head}>
              <h3>{page.bands[band]}</h3>
              {summary && <span>{AGREEMENT[summary.agreement] ?? summary.agreement}</span>}
            </header>
            <div className={styles.tiles}>
              {page.horizons.filter((h) => h.band === band).map((meta) => (
                <Tile
                  key={meta.key}
                  label={meta.label}
                  read={reads.get(meta.key)}
                  combined={page.evaluation[meta.key]?.combined}
                  measuring={page.errors[partOf(meta.interval)] === 'measuring'}
                  selected={selected === meta.key}
                  onSelect={() => onSelect(meta.key)}
                />
              ))}
            </div>
          </section>
        )
      })}
    </div>
  )
}

function Tile({ label, read, combined, measuring, selected, onSelect }: {
  label: string
  read?: HorizonRead
  combined?: CombinedReading
  measuring: boolean
  selected: boolean
  onSelect: () => void
}) {
  const lean = combined?.lean ?? 'unweighted'
  const ready = read?.available && read.trend && read.momentum
  return (
    <button type="button" className={`${styles.tile} ${selected ? styles.selected : ''}`} aria-pressed={selected} onClick={onSelect}>
      <span className={styles.label}>{label}</span>
      {ready && read?.trend && read.momentum ? (
        <>
          <span className={`${styles.lean} ${styles[lean]}`}>
            {COMBINED_LABEL[lean]}{combined?.score != null ? ` ${combined.score > 0 ? '+' : ''}${combined.score.toFixed(2)}` : ''}
          </span>
          <span className={styles.line}>
            <b className={read.trend.state.startsWith('above') ? styles.upText : styles.downText}>{read.trend.state.startsWith('above') ? '▲' : '▼'}</b>
            {' '}{signedPct(read.trend.distance_pct)} vs {read.trend.ma_label} avg
          </span>
          <span className={styles.line}>{signedPct(read.momentum.change_pct, 2)} over the last {label}</span>
        </>
      ) : (
        <span className={styles.muted}>{measuring ? 'measuring…' : read?.reason ?? 'not measured yet'}</span>
      )}
    </button>
  )
}
