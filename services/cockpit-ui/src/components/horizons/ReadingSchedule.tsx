import { useState } from 'react'
import { useReadingSchedule, useSaveReadingSchedule } from '../../api/hooks/useReadingSchedule'
import type { BandKey } from '../../api/horizonTypes'
import { TIME_PATTERN, changeLine, confirmQuestion, lastLine, scheduleLine } from './readingScheduleText'
import styles from './ReadingSchedule.module.css'

/**
 * The band's Hermes reading schedule beside its reading: the next scheduled
 * reading or "Schedule off", what happened at the last slot, and the last change
 * with who made it and what it replaced. Off by default; saving asks first,
 * because every reading uses Hermes compute.
 */
export function ReadingSchedule({ symbol, band, label }: { symbol: string; band: BandKey; label: string }) {
  const schedule = useReadingSchedule(symbol)
  const save = useSaveReadingSchedule(symbol)
  const entry = schedule.data?.bands[band]
  const lastChange = schedule.data?.changes.find((change) => change.scope === band)
  const [editing, setEditing] = useState(false)
  const [enabled, setEnabled] = useState(false)
  const [time, setTime] = useState('08:00')
  const valid = TIME_PATTERN.test(time)
  const last = lastLine(entry)

  const edit = () => {
    setEnabled(entry?.enabled ?? false)
    setTime(entry?.daily_time ?? '08:00')
    setEditing(true)
  }
  const submit = () => {
    if (!valid || !window.confirm(confirmQuestion(symbol, label, enabled, time))) return
    save.mutate({ scope: band, enabled, daily_time: time }, { onSuccess: () => setEditing(false) })
  }

  return (
    <div className={styles.schedule} aria-label={`Hermes reading schedule for the ${label.toLowerCase()}`}>
      <div className={styles.row}>
        <span className={entry?.enabled ? styles.on : styles.off}>
          {schedule.isError ? `Schedule unavailable: ${(schedule.error as Error).message}` : scheduleLine(entry)}
        </span>
        <button type="button" className="chip" disabled={!schedule.data} onClick={editing ? () => setEditing(false) : edit}>
          {editing ? 'cancel' : 'edit schedule'}
        </button>
      </div>
      {last && <p className={styles.meta}>{last}</p>}
      {lastChange && <p className={styles.meta}>{changeLine(lastChange)}</p>}
      {editing && (
        <div className={styles.form}>
          <label className={styles.check}>
            <input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} /> read every day
          </label>
          <label className={styles.time}>
            at <input type="time" step={60} value={time} onChange={(event) => setTime(event.target.value)} /> UTC
          </label>
          <button type="button" className="chip" disabled={!valid || save.isPending} onClick={submit}>{save.isPending ? 'saving…' : 'save'}</button>
        </div>
      )}
      {save.error && <p className={styles.warn}>{(save.error as Error).message}</p>}
    </div>
  )
}
