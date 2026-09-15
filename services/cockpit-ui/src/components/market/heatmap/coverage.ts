/** How much of a heatmap window the recorded books fill, stated beside the chart. */

const BUCKET_WORDS: Record<number, string> = {
  300: 'five-minute',
  900: 'fifteen-minute',
  3600: 'hourly',
  7200: 'two-hour',
  28800: 'eight-hour',
}

export function bucketWords(seconds: number): string {
  return BUCKET_WORDS[seconds] ?? `${Math.round(seconds / 60)}-minute`
}

export function coverage(booksPerBucket: number[]): { filled: number; total: number } {
  return { filled: booksPerBucket.filter((n) => n > 0).length, total: booksPerBucket.length }
}

/** "Recorded books since 14 Sep, 12:38 · 7 of 84 two-hour buckets filled in this window." */
export function coverageLine(
  data: { books_per_bucket: number[]; bucket_seconds: number; recording_since: string | null },
  when: (iso: string | null | undefined) => string,
): string {
  if (!data.recording_since) return 'No books recorded for this market yet.'
  const { filled, total } = coverage(data.books_per_bucket)
  return `Recorded books since ${when(data.recording_since)} · ${filled} of ${total} ${bucketWords(data.bucket_seconds)} buckets filled in this window.`
}
