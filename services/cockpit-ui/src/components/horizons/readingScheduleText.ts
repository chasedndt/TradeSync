import type { BandSchedule, ScheduleChangeRecord, ScheduleValue } from '../../api/readingScheduleTypes'

export const TIME_PATTERN = /^([01][0-9]|2[0-3]):([0-5][0-9])$/

const RESULT_WORDS: Record<string, string> = {
  started: 'reading started',
  skipped: 'skipped',
  missed: 'missed',
  failed: 'failed to start',
  starting: 'starting',
}

/** "15 Sep, 09:30": an absolute local time. */
export const localTime = (iso: string | null | undefined): string =>
  iso ? new Date(iso).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—'

export function scheduleLine(band: Pick<BandSchedule, 'enabled' | 'daily_time' | 'next_reading_at'> | undefined): string {
  if (!band) return 'Reading the schedule…'
  if (!band.enabled || !band.next_reading_at) return 'Schedule off'
  return `Next scheduled reading ${localTime(band.next_reading_at)} · daily at ${band.daily_time} UTC`
}

export function lastLine(band: Pick<BandSchedule, 'last'> | undefined): string | null {
  const last = band?.last
  if (!last?.slot) return null
  const words = RESULT_WORDS[last.result ?? ''] ?? last.result ?? 'no result recorded'
  return `Last scheduled slot ${localTime(last.slot)}: ${words}${last.detail ? ` (${last.detail})` : ''}`
}

export function valueWords(value: ScheduleValue | null): string {
  if (!value) return 'no schedule (off)'
  if (value.enabled) return `daily at ${value.daily_time} UTC`
  return value.daily_time ? `off (time ${value.daily_time} UTC kept)` : 'off'
}

export function changeLine(change: Pick<ScheduleChangeRecord, 'changed_by' | 'changed_at' | 'previous' | 'next'>): string {
  return `Set to ${valueWords(change.next)} by ${change.changed_by} at ${localTime(change.changed_at)}; was ${valueWords(change.previous)}`
}

export function confirmQuestion(symbol: string, label: string, enabled: boolean, time: string): string {
  return enabled
    ? `Read the ${label.toLowerCase()} for ${symbol} with Hermes every day at ${time} UTC? Each reading uses Hermes compute.`
    : `Turn off the scheduled Hermes reading of the ${label.toLowerCase()} for ${symbol}?`
}
