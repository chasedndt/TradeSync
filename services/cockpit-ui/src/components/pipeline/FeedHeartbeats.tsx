import type { PipelineFeeds } from '../../api/pipelineFeedTypes'
import { ago, countsLine, deliveryLabel, feedTone, lastDelivery, stamp, stateLabel } from './feedText'
import styles from './FeedHeartbeats.module.css'

/**
 * The feeds added on 14 September, beside the stages they feed: whether each is
 * connected, when it last delivered, what it counted in the last hour, how often
 * it reconnected and its last error, with a plain marker where its data carries
 * no scoring influence. Ages count to the moment the heartbeats were read.
 */
export function FeedHeartbeats({ feeds }: { feeds: PipelineFeeds | undefined }) {
  if (!feeds) {
    return (
      <section className="panel pipeline-section" aria-labelledby="feed-heartbeats-title">
        <div className="panel-heading pipeline-section-heading">
          <div><h2 id="feed-heartbeats-title">Feed heartbeats</h2><p>Streams, fetches and loops added on 14 September.</p></div>
        </div>
        <p className={styles.empty}>This inspection carried no feed heartbeats; the state API answering it predates them.</p>
      </section>
    )
  }
  const readMs = Date.parse(feeds.generated_at)
  const unavailable = Object.entries(feeds.sources).filter(([, source]) => !source.ok)
  const connected = feeds.feeds.filter((feed) => feed.connected).length

  return (
    <section className="panel pipeline-section" aria-labelledby="feed-heartbeats-title">
      <div className="panel-heading pipeline-section-heading">
        <div>
          <h2 id="feed-heartbeats-title">Feed heartbeats</h2>
          <p>Streams, fetches and loops added on 14 September · read <time dateTime={feeds.generated_at}>{stamp(feeds.generated_at)}</time></p>
        </div>
        <span>{connected}/{feeds.feeds.length} connected or answering</span>
      </div>
      {unavailable.map(([name, source]) => (
        <p key={name} className={styles.warn}>{source.reason ?? `${name} did not report its feeds`}; its feeds are not listed.</p>
      ))}
      <div className="table-scroll">
        <table className={styles.table}>
          <thead><tr><th>Feed</th><th>State</th><th>Last delivered</th><th>Last hour</th><th>Reconnects</th><th>Last error</th></tr></thead>
          <tbody>
            {feeds.feeds.map((feed) => {
              const delivered = lastDelivery(feed)
              const newestRow = typeof feed.detail.newest_row_at === 'string' ? feed.detail.newest_row_at : null
              return (
                <tr key={feed.id}>
                  <td>
                    <span className={styles.label}>{feed.label}</span>
                    <small className={styles.sub}>{feed.service} · {feed.kind}</small>
                    {!feed.scoring_influence && <span className={styles.context}>context only · no scoring influence</span>}
                    <small className={styles.influence}>{feed.influence}</small>
                  </td>
                  <td>
                    <span className={`pipeline-state pipeline-state--${feedTone(feed)}`}><span className="status-dot" />{stateLabel(feed)}</span>
                    {feed.state_since && <small className={styles.sub}>since {stamp(feed.state_since)}</small>}
                  </td>
                  <td>
                    {delivered
                      ? <><time className={styles.mono} dateTime={delivered}>{stamp(delivered)}</time><small className={styles.sub}>{deliveryLabel(feed)} · {ago(delivered, readMs)}</small></>
                      : <span className="tone-dim">nothing delivered yet</span>}
                    {newestRow && <small className={styles.sub}>newest funding hour {stamp(newestRow)}</small>}
                  </td>
                  <td className={styles.mono}>{countsLine(feed.counts_1h)}</td>
                  <td className={styles.mono}>{feed.kind === 'websocket' ? feed.reconnects : '—'}</td>
                  <td>
                    {feed.last_error
                      ? <><span className={styles.error}>{feed.last_error}</span><small className={styles.sub}>{stamp(feed.last_error_at)}</small></>
                      : <span className="tone-dim">none since start</span>}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className={styles.note}>
        {feeds.note} Counting since {Object.entries(feeds.sources).map(([name, source]) => `${name} ${stamp(source.counting_since)}`).join(' · ')}.
      </p>
    </section>
  )
}
