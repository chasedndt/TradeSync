import { useMemo, useState } from 'react'
import { useAgentFeed, useHarnessStatus } from '../api/hooks/useAgentFeed'
import { AgentFeedItem, kindOf } from './AgentsFeedItem'
import { SourceCards } from '../components/SourceCards'
import { HermesPanel } from '../components/agents/HermesPanel'
import styles from './Agents.module.css'

/**
 * The Agents page: what the ChaseOS fleet produced, from both bridges
 * (Discord posts and Hermes job outputs), held in quarantine with provenance
 * and grouped by the agent that produced it. Everything here is untrusted
 * material. It scores nothing until an agent's claims are recorded against
 * outcomes and earn a weight on the evidence cards, and promotion stays an
 * operator act.
 */
export function Agents() {
  const feed = useAgentFeed(200)
  const harness = useHarnessStatus()
  const [selected, setSelected] = useState<string | null>(null)

  const rows = feed.items
  const agents = useMemo(() => {
    const by = new Map<string, { kind: string; count: number; latest: string }>()
    for (const r of rows) {
      const cur = by.get(r.payload.agent)
      if (!cur) by.set(r.payload.agent, { kind: kindOf(r.payload), count: 1, latest: r.received_at })
      else { cur.count += 1; if (r.received_at > cur.latest) cur.latest = r.received_at }
    }
    return [...by.entries()].sort((a, b) => (a[1].latest < b[1].latest ? 1 : -1))
  }, [rows])
  const visible = selected ? rows.filter((r) => r.payload.agent === selected) : rows

  return (
    <div className={styles.page}>
      <section className={`panel ${styles.hero}`}>
        <div>
          <div className={styles.kicker}>ChaseOS agents · read-only bridges · quarantine</div>
          <h2>What the fleet is saying, in one place.</h2>
          <p>
            Two bridges copy the fleet's work into quarantine with who, where and when: the discord-reader for channel posts,
            and the host bridge for every Hermes job run, including the ones that never reach Discord.
            Nothing here is a signal. An agent earns a weight only when its claims are measured against outcomes on the evidence cards.
          </p>
        </div>
        <div className={styles.status}>
          <span>Advisory harness runtime</span>
          <strong className={harness.data?.status === 'live' ? 'tone-good' : 'tone-dim'}>
            {harness.data?.status ?? '…'}{harness.data?.models?.length ? ` · ${harness.data.models.join(', ')}` : ''}
          </strong>
          <span>may explain and compare · may not score, approve or execute</span>
        </div>
      </section>

      <HermesPanel />

      <SourceCards />

      <div className={styles.layout}>
        <section className="panel">
          <div className="panel-heading"><div><h3>Agents</h3><p>{agents.length} producing · {rows.length} items held</p></div></div>
          <ul className={styles.agents}>
            <li>
              <button type="button" className={`${styles.agent} ${selected === null ? styles.agentActive : ''}`} onClick={() => setSelected(null)}>
                <span>All agents</span><span className={styles.count}>{rows.length}</span>
              </button>
            </li>
            {agents.map(([name, a]) => (
              <li key={name}>
                <button type="button" className={`${styles.agent} ${selected === name ? styles.agentActive : ''}`} onClick={() => setSelected(name)}>
                  <span>{name}<small>{a.kind} · last {new Date(a.latest).toUTCString().slice(17, 22)} UTC</small></span>
                  <span className={styles.count}>{a.count}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>

        <section className="panel">
          <div className="panel-heading">
            <div><h3>Feed{selected ? ` · ${selected}` : ''}</h3><p>newest first · sources: discord, chaseos · authority: none</p></div>
            {feed.isError && <span className="tone-bad">feed unavailable</span>}
          </div>
          {visible.length === 0 ? (
            <div className={styles.empty}>
              {feed.isLoading ? 'Reading quarantine…' : (
                <>
                  Nothing held yet. The host bridge (<code>tools/hermes_output_bridge.py</code>) files Hermes job runs as they happen;
                  the discord-reader starts when <code>DISCORD_BOT_TOKEN</code> and <code>DISCORD_READER_CHANNELS</code> are set in runtime.env.
                  Both read forward from the moment they start.
                </>
              )}
            </div>
          ) : (
            <ul className={styles.feed}>{visible.map((r) => <AgentFeedItem key={r.id} item={r} />)}</ul>
          )}
          {feed.note && <p className={styles.foot}>{feed.note}</p>}
        </section>
      </div>
    </div>
  )
}
