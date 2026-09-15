import { useState } from 'react'
import { EvidenceCombinationPanel } from './combination/EvidenceCombinationPanel'
import { FailureList } from './FailureList'
import { ProposalList } from './ProposalList'
import { Scoreboard } from './Scoreboard'
import { VerdictTable } from './VerdictTable'
import { HORIZONS, horizonLabel, readOperator, saveOperator } from './format'
import styles from './LearningView.module.css'

const WINDOWS = [7, 14, 30]

/**
 * Learning, on the Opportunities page: how the paper calls did after costs,
 * what misled the ones that failed, which readings help or hurt, and the
 * weight proposals an operator may adopt. Nothing here adopts on its own.
 */
export function LearningView() {
  const [days, setDays] = useState(14)
  const [horizon, setHorizon] = useState<number>(60)
  const [operator, setOperator] = useState<string>(readOperator)

  return (
    <div className={styles.view}>
      <div className={styles.filters}>
        <div className={styles.group} role="group" aria-label="Window">
          <span className={styles.label}>Window</span>
          {WINDOWS.map((span) => (
            <button key={span} type="button" className={days === span ? 'chip chip--active' : 'chip'} aria-pressed={days === span} onClick={() => setDays(span)}>
              {span}d
            </button>
          ))}
        </div>
        <div className={styles.group} role="group" aria-label="Horizon">
          <span className={styles.label}>Horizon</span>
          {HORIZONS.map((minutes) => (
            <button key={minutes} type="button" className={horizon === minutes ? 'chip chip--active' : 'chip'} aria-pressed={horizon === minutes} onClick={() => setHorizon(minutes)}>
              {horizonLabel(minutes)}
            </button>
          ))}
        </div>
        <label className={styles.operator}>
          <span className={styles.label}>Your name</span>
          <input
            value={operator}
            maxLength={80}
            autoComplete="name"
            placeholder="Recorded with adopt, reject and revert"
            onChange={(event) => {
              setOperator(event.target.value)
              saveOperator(event.target.value)
            }}
          />
        </label>
      </div>
      <Scoreboard days={days} selectedHorizon={horizon} />
      <ProposalList operator={operator} horizon={horizon} />
      <FailureList horizon={horizon} />
      <VerdictTable horizon={horizon} days={days} />
      <EvidenceCombinationPanel horizon={horizon} />
    </div>
  )
}
