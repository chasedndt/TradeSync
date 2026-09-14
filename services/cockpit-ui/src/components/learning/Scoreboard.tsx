import { useLearningScoreboard } from '../../api/hooks/useLearning'
import type { HorizonScore } from '../../api/learningTypes'
import { DailyNetChart } from './DailyNetChart'
import {
  CLASSIFICATION_LABELS,
  CLASSIFICATION_ORDER,
  horizonLabel,
  netTone,
  pctRange,
  shareRange,
  sharePct,
  signedPct,
} from './format'
import styles from './Scoreboard.module.css'

/** The paper track record by horizon, net of round-trip costs, overall and day by day. */
export function Scoreboard({ days, selectedHorizon }: { days: number; selectedHorizon: number }) {
  const { data, isLoading, error } = useLearningScoreboard(days)

  return (
    <section className="panel" aria-labelledby="learning-scoreboard-title">
      <div className="panel-heading">
        <div>
          <h3 id="learning-scoreboard-title">Scoreboard after costs</h3>
          <p>
            {data
              ? `${data.attributions.toLocaleString()} attributed horizons · last ${data.days} days · ${data.cost_pct.toFixed(2)}% round trip per call`
              : `last ${days} days`}
          </p>
        </div>
      </div>
      {isLoading ? (
        <p className={styles.message}>Loading the scoreboard…</p>
      ) : error ? (
        <p className={styles.message}>Scoreboard unavailable: {(error as Error).message}</p>
      ) : !data?.horizons.length ? (
        <p className={styles.message}>No measured outcome has been attributed in this window yet.</p>
      ) : (
        <div className={styles.rows}>
          {data.horizons.map((score) => (
            <HorizonRow key={score.horizon_minutes} score={score} selected={score.horizon_minutes === selectedHorizon} />
          ))}
        </div>
      )}
      {data && (
        <p className={styles.foot}>
          {data.note} Intervals are 95% and use an effective sample that counts calls in the same horizon-long window as one cluster.
        </p>
      )}
    </section>
  )
}

function HorizonRow({ score, selected }: { score: HorizonScore; selected: boolean }) {
  const label = `${horizonLabel(score.horizon_minutes)} horizon`
  return (
    <div className={`${styles.row} ${selected ? styles.selected : ''}`} aria-current={selected ? 'true' : undefined}>
      <div className={styles.summary}>
        <h4 className={styles.horizon}>{label}</h4>
        <p className={styles.sub}>{score.attributions.toLocaleString()} calls · effective sample {Math.round(score.effective_samples)}</p>
        <div className={styles.stats}>
          <div className={styles.stat}>
            <span>Won after costs</span>
            <strong>{sharePct(score.net_hit_rate)}</strong>
            <small>{shareRange(score.net_hit_rate_low, score.net_hit_rate_high)}</small>
          </div>
          <div className={styles.stat}>
            <span>Mean net return</span>
            <strong className={netTone(score.mean_net_return_pct)}>{signedPct(score.mean_net_return_pct, 3)}</strong>
            <small>{pctRange(score.mean_net_return_low, score.mean_net_return_high, 3)}</small>
          </div>
        </div>
        <ul className={styles.classes} aria-label={`${label} results by class`}>
          {CLASSIFICATION_ORDER.map((classification) => (
            <li key={classification}>
              <span>{CLASSIFICATION_LABELS[classification]}</span>
              <b>{(score.classifications[classification] ?? 0).toLocaleString()}</b>
            </li>
          ))}
        </ul>
      </div>
      <DailyNetChart daily={score.daily} label={label} />
    </div>
  )
}
