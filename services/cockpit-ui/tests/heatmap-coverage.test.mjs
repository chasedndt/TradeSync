import { test } from 'node:test'
import assert from 'node:assert/strict'
import { importTs } from './support/importTs.mjs'

const { bucketWords, coverage, coverageLine } = await importTs('src/components/market/heatmap/coverage.ts')

test('coverage counts the window buckets that hold books and names their size', () => {
  assert.deepEqual(coverage([0, 0, 3, 8, 0, 120]), { filled: 3, total: 6 })
  assert.equal(bucketWords(7200), 'two-hour')
  assert.equal(bucketWords(28800), 'eight-hour')
  assert.equal(bucketWords(1800), '30-minute')
})

test('the panel states when recording began and how much of the window is filled', () => {
  const when = (iso) => (iso ? '14 Sep, 12:38' : '—')
  assert.equal(coverageLine({ books_per_bucket: [0, 8, 8], bucket_seconds: 7200, recording_since: '2026-09-14T11:38:00+00:00' }, when),
    'Recorded books since 14 Sep, 12:38 · 2 of 3 two-hour buckets filled in this window.')
  assert.equal(coverageLine({ books_per_bucket: [0, 0], bucket_seconds: 28800, recording_since: null }, when),
    'No books recorded for this market yet.')
})
