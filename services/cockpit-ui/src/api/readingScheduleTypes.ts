/** The Hermes reading schedule per market and band: off unless an operator sets one; times are UTC. */

import type { BandKey } from './horizonTypes'

export interface ScheduleValue {
  enabled: boolean
  daily_time: string | null
}

export interface BandSchedule {
  enabled: boolean
  /** "HH:MM" in UTC; kept while a schedule is off. */
  daily_time: string | null
  next_reading_at: string | null
  updated_by: string | null
  updated_at: string | null
  last: { slot: string | null; result: string | null; detail: string | null } | null
}

export interface ScheduleChangeRecord {
  scope: BandKey
  changed_by: string
  changed_at: string
  /** Null when the band had no schedule before this change. */
  previous: ScheduleValue | null
  next: ScheduleValue
}

export interface ReadingSchedule {
  schema_version: 'horizon_reading_schedule_v1'
  symbol: string
  generated_at: string
  timezone: 'UTC'
  grace_minutes: number
  bands: Record<BandKey, BandSchedule>
  changes: ScheduleChangeRecord[]
  note: string
}
