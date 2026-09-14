import type { DepthResponse } from '../../api/types'
import { DepthLadder } from './DepthLadder'

interface Props {
  depth?: DepthResponse
  isLoading: boolean
  isError: boolean
}

/** The current book, shown beside the chart rather than drawn across candles. */
export function OrderBookPanel({ depth, isLoading, isError }: Props) {
  return (
    <section className="panel" style={{ padding: 16, marginTop: 16 }}>
      <div className="panel-heading" style={{ marginBottom: 10 }}>
        <div>
          <h2 style={{ fontSize: 17 }}>Order book</h2>
          <p>
            Resting size right now. Not a series — the book is replaced on
            every poll, so it is shown beside the chart rather than drawn
            across candles it was never present for.
          </p>
        </div>
      </div>
      <DepthLadder
        depth={depth}
        isLoading={isLoading}
        isError={isError}
      />
    </section>
  )
}
