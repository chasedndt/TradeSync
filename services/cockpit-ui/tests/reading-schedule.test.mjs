import { test } from 'node:test'
import assert from 'node:assert/strict'
import { importTs } from './support/importTs.mjs'

const { TIME_PATTERN, changeLine, confirmQuestion, lastLine, scheduleLine, valueWords } = await importTs('src/components/horizons/readingScheduleText.ts')

test('a band reads "Schedule off" until it is enabled, then names its next reading and daily time', () => {
  assert.equal(scheduleLine(undefined), 'Reading the schedule…')
  assert.equal(scheduleLine({ enabled: false, daily_time: '07:30', next_reading_at: null }), 'Schedule off')
  assert.match(scheduleLine({ enabled: true, daily_time: '07:30', next_reading_at: '2026-09-16T07:30:00+00:00' }),
    /^Next scheduled reading .+ · daily at 07:30 UTC$/)
})

test('the last slot and the last change say what happened, who changed it and what it replaced', () => {
  assert.equal(lastLine({ last: null }), null)
  assert.match(lastLine({ last: { slot: '2026-09-15T07:30:00+00:00', result: 'skipped', detail: 'a reading is already running' } }),
    /^Last scheduled slot .+: skipped \(a reading is already running\)$/)
  assert.match(lastLine({ last: { slot: '2026-09-15T07:30:00+00:00', result: 'started', detail: null } }), /: reading started$/)
  assert.equal(valueWords(null), 'no schedule (off)')
  assert.equal(valueWords({ enabled: true, daily_time: '07:30' }), 'daily at 07:30 UTC')
  assert.equal(valueWords({ enabled: false, daily_time: '07:30' }), 'off (time 07:30 UTC kept)')
  assert.match(changeLine({ changed_by: 'chase', changed_at: '2026-09-15T01:00:00Z', previous: null, next: { enabled: true, daily_time: '07:30' } }),
    /^Set to daily at 07:30 UTC by chase at .+; was no schedule \(off\)$/)
})

test('times are HH:MM on the clock, and the confirmation names the compute it uses', () => {
  assert.ok(TIME_PATTERN.test('07:30') && !TIME_PATTERN.test('7:30') && !TIME_PATTERN.test('24:00'))
  assert.equal(confirmQuestion('BTC-PERP', 'Lower time frame', true, '07:30'),
    'Read the lower time frame for BTC-PERP with Hermes every day at 07:30 UTC? Each reading uses Hermes compute.')
  assert.equal(confirmQuestion('BTC-PERP', 'Lower time frame', false, '07:30'),
    'Turn off the scheduled Hermes reading of the lower time frame for BTC-PERP?')
})
