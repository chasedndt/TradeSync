import { useState } from 'react'
import type { usePaperRiskActions } from '../../../api/hooks/usePaperRisk'
import type { LimitValues, RiskState } from '../../../api/paperRiskTypes'
import { ConfirmDialog } from './ConfirmDialog'
import { LIMIT_FIELDS, inputValue, limitText, parseLimit, utcStamp } from './paperRiskFormat'
import type { LimitField } from './paperRiskFormat'
import { rememberOperator, rememberedOperator } from './paperRiskOperator'
import styles from './LimitsEditor.module.css'

type Limits = NonNullable<RiskState['limits']>
type Mutation = ReturnType<typeof usePaperRiskActions>['limits']

const UNIT: Record<LimitField['unit'], string> = { usdc: 'USDC', percent: '%', count: 'positions', seconds: 'seconds', ratio: '0 to 1' }

/** Operator-edited limits: every change needs a name, a reason and a confirmation, and is recorded with the previous values. */
export function LimitsEditor({ limits, mutation }: { limits: Limits; mutation: Mutation }) {
  const [draft, setDraft] = useState<Partial<Record<keyof LimitValues, string>>>({})
  const [operator, setOperator] = useState(rememberedOperator)
  const [reason, setReason] = useState('')
  const [confirming, setConfirming] = useState(false)

  const invalid = LIMIT_FIELDS.filter((field) => draft[field.key] !== undefined && parseLimit(field, draft[field.key] ?? '') === null)
  const changes = LIMIT_FIELDS.flatMap((field) => {
    const parsed = draft[field.key] === undefined ? null : parseLimit(field, draft[field.key] ?? '')
    return parsed === null || parsed === limits.values[field.key] ? [] : [{ field, value: parsed }]
  })
  const ready = changes.length > 0 && invalid.length === 0 && operator.trim().length > 0 && reason.trim().length >= 5

  const apply = () => {
    setConfirming(false)
    rememberOperator(operator)
    mutation.mutate(
      { operator: operator.trim(), reason: reason.trim(), ...Object.fromEntries(changes.map(({ field, value }) => [field.key, value])) },
      { onSuccess: () => { setDraft({}); setReason('') } },
    )
  }

  return (
    <details className={styles.editor}>
      <summary>Limits · last changed by {limits.operator} at {utcStamp(limits.updated_at)}</summary>
      <p>{limits.reason}</p>
      <form onSubmit={(event) => { event.preventDefault(); if (ready) setConfirming(true) }}>
        <div className={styles.fields}>
          {LIMIT_FIELDS.map((field) => (
            <label key={field.key}>
              {field.label} ({UNIT[field.unit]})
              <input
                inputMode="decimal"
                value={draft[field.key] ?? inputValue(field, limits.values[field.key])}
                aria-invalid={invalid.includes(field)}
                onChange={(event) => setDraft({ ...draft, [field.key]: event.target.value })}
              />
            </label>
          ))}
        </div>
        <div className={styles.fields}>
          <label>Operator<input value={operator} maxLength={80} onChange={(event) => setOperator(event.target.value)} /></label>
          <label>Reason<input value={reason} maxLength={240} placeholder="Why the limits change" onChange={(event) => setReason(event.target.value)} /></label>
        </div>
        {invalid.length > 0 && <p className="tone-warn">Out of range: {invalid.map((field) => field.label).join(', ')}.</p>}
        <button type="submit" className="chip" disabled={!ready || mutation.isPending}>
          {mutation.isPending ? 'Saving limits…' : `Review ${changes.length || ''} limit change${changes.length === 1 ? '' : 's'}`}
        </button>
      </form>
      {mutation.isError && <p role="alert" className="tone-bad">{mutation.error.message}</p>}
      {mutation.isSuccess && <p role="status">Limits changed and recorded with the previous values. Nothing raises a limit automatically.</p>}
      {confirming && (
        <ConfirmDialog
          title="Change paper limits?"
          body={changes.map(({ field, value }) => `${field.label}: ${limitText(field, limits.values[field.key])} to ${limitText(field, value)}`).join('; ')}
          confirmLabel="Change limits"
          busy={mutation.isPending}
          onConfirm={apply}
          onCancel={() => setConfirming(false)}
        />
      )}
    </details>
  )
}
