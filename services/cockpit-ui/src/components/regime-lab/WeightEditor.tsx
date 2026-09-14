import type { RegimeLabBlockEvidence } from '../../api/regimeLabTypes'
import { MAX_BLOCK_WEIGHT, lockedReason, type WeightCheck, type WeightDraft } from './challengerForm'
import { blockLabel } from './format'
import styles from './WeightEditor.module.css'

interface Props {
  blocks: string[]
  baseline: Record<string, number>
  evidence: Record<string, RegimeLabBlockEvidence>
  draft: WeightDraft
  check: WeightCheck
  onChange: (block: string, raw: string) => void
  onReset: () => void
}

const issueText = (issue: string) =>
  issue === 'empty' ? 'Enter a weight; an empty entry is not read as zero.' : `This weight is ${issue}.`

/** The five block weights as typed text; a block with no admitted features keeps its baseline weight. */
export function WeightEditor({ blocks, baseline, evidence, draft, check, onChange, onReset }: Props) {
  const atBaseline = blocks.every((block) => draft[block] === (baseline[block] ?? 0).toFixed(2))
  return (
    <div className={styles.editor}>
      <div className={styles.head}>
        <span>Block weights, each at most {MAX_BLOCK_WEIGHT.toFixed(2)}</span>
        <button type="button" className={styles.reset} onClick={onReset} disabled={atBaseline}>Reset to baseline</button>
      </div>
      {blocks.map((block) => {
        const locked = lockedReason(evidence[block], baseline[block] ?? 0)
        const issue = check.issues[block]
        const noteId = `weight-note-${block}`
        const typed = Number(draft[block])
        const slider = Number.isFinite(typed) ? Math.min(Math.max(typed, 0), MAX_BLOCK_WEIGHT) : 0
        return (
          <div className={styles.row} key={block}>
            <label className={styles.label} htmlFor={`weight-${block}`}>
              {blockLabel(block)}
              <small>baseline {(baseline[block] ?? 0).toFixed(2)}</small>
            </label>
            <input
              className={styles.slider}
              type="range"
              min={0}
              max={MAX_BLOCK_WEIGHT}
              step={0.01}
              value={slider}
              disabled={locked !== null}
              aria-label={`${blockLabel(block)} weight slider`}
              onChange={(event) => onChange(block, Number(event.target.value).toFixed(2))}
            />
            <input
              id={`weight-${block}`}
              className={`${styles.number} ${issue ? styles.invalid : ''}`}
              inputMode="decimal"
              autoComplete="off"
              value={draft[block] ?? ''}
              disabled={locked !== null}
              aria-invalid={Boolean(issue)}
              aria-describedby={locked || issue ? noteId : undefined}
              onChange={(event) => onChange(block, event.target.value)}
            />
            {locked && <p id={noteId} className={styles.locked}>{locked}</p>}
            {!locked && issue && <p id={noteId} className={styles.issue}>{issueText(issue)}</p>}
          </div>
        )
      })}
      <div className={`${styles.total} ${check.sumsToOne ? styles.totalOk : styles.totalBad}`} role="status">
        <span>Total</span>
        <strong>{check.sum.toFixed(2)}</strong>
        <small>
          {check.sumsToOne
            ? 'Adds to 1.00'
            : Object.keys(check.issues).length > 0
              ? 'Every weight needs a valid number before the total counts'
              : 'Must add to exactly 1.00'}
        </small>
      </div>
    </div>
  )
}
