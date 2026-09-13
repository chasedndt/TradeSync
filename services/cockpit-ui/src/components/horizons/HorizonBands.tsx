import type { BandKey, HorizonKey, HorizonPage } from '../../api/horizonTypes'
import { HorizonCard } from './HorizonCard'
import { LEAN_LABEL } from './horizonText'
import type { LinkTarget } from './LinkedText'
import styles from './HorizonBands.module.css'

const AGREEMENT: Record<string, string> = {
  up: 'both records lean higher',
  down: 'both records lean lower',
  mixed: 'no consistent direction',
  split: 'the horizons disagree',
  unjudged: 'too thin to judge',
}

interface Props {
  page: HorizonPage
  selected: HorizonKey
  targets: LinkTarget[]
  onSelect: (key: HorizonKey) => void
  onPickFeature: (key: string, horizon: HorizonKey) => void
}

/** Lower, medium and higher time frames side by side, each with its two horizons. */
export function HorizonBands({ page, selected, targets, onSelect, onPickFeature }: Props) {
  const reads = page.outlook.horizons ?? []
  const bands = page.outlook.bands ?? []
  return (
    <div className={styles.bands}>
      {(Object.keys(page.bands) as BandKey[]).map((band) => {
        const summary = bands.find((b) => b.band === band)
        const agreement = summary?.agreement ?? 'unjudged'
        return (
          <section key={band} className={`panel ${styles.band}`} aria-label={page.bands[band]}>
            <header className={styles.bandHead}>
              <h3>{page.bands[band]}</h3>
              <span className={styles.agreement} title={Object.entries(summary?.leans ?? {}).map(([k, v]) => `${k}: ${LEAN_LABEL[v as keyof typeof LEAN_LABEL] ?? v}`).join(' · ')}>
                {AGREEMENT[agreement] ?? agreement}
              </span>
            </header>
            {reads.filter((r) => r.band === band).map((read) => (
              <HorizonCard
                key={read.key}
                read={read}
                evaluation={page.evaluation[read.key]}
                selected={selected === read.key}
                targets={targets}
                onSelect={() => onSelect(read.key)}
                onPickFeature={(key) => onPickFeature(key, read.key)}
              />
            ))}
          </section>
        )
      })}
    </div>
  )
}
