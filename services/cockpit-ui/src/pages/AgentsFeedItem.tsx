import type { AgentPost } from '../api/hooks/useAgentFeed'
import type { AgentPostPayload, DiscordMessagePayload, HermesJobOutputPayload } from '../api/types'
import styles from './Agents.module.css'

const kindPill: Record<string, string> = {
  agent: styles.pillAgent,
  alerts: styles.pillAlerts,
  operator: styles.pillOperator,
  job: styles.pillAgent,
}

/** The stream kind shown beside an agent: channel kind for Discord posts, "job" for Hermes runs. */
export function kindOf(p: AgentPostPayload): string {
  return p.kind === 'discord_message' ? p.channel_kind : 'job'
}

/** One held item: who, where, when, what, and whether intake accepted it. */
export function AgentFeedItem({ item }: { item: AgentPost }) {
  const p = item.payload
  return (
    <li className={styles.item}>
      <div className={styles.meta}>
        <strong>{p.agent}</strong>
        <span className={`${styles.pill} ${kindPill[kindOf(p)] ?? styles.pillOperator}`}>{kindOf(p)}</span>
        {p.kind === 'discord_message' ? <DiscordMeta p={p} received={item.received_at} /> : <HermesMeta p={p} received={item.received_at} />}
        {!item.accepted && <span className={`${styles.pill} ${styles.pillRefused}`}>refused at intake</span>}
        {item.promoted_to && <span className={`${styles.pill} ${styles.pillOperator}`}>promoted: {item.promoted_to}</span>}
      </div>
      {p.content && <p className={styles.content}>{p.content}</p>}
      {p.kind === 'discord_message' && <DiscordExtras p={p} />}
      {!item.accepted && item.reasons.length > 0 && (
        <span className={styles.reasons}>{item.reasons.map((r) => `${r.code}: ${r.detail}`).join(' · ')}</span>
      )}
    </li>
  )
}

function DiscordMeta({ p, received }: { p: DiscordMessagePayload; received: string }) {
  const when = p.posted_at ? new Date(p.posted_at) : new Date(received)
  return (
    <>
      <span>{p.author.name}{p.author.bot ? ' (bot)' : ''}</span>
      <time dateTime={when.toISOString()}>{when.toUTCString()}</time>
    </>
  )
}

function HermesMeta({ p, received }: { p: HermesJobOutputPayload; received: string }) {
  return (
    <>
      <span>job {p.job_id}{p.schedule ? ` · ${p.schedule}` : ''}{p.job_enabled ? '' : ' · disabled'}</span>
      <span>
        {p.delivery.kind === 'discord' ? `delivered to ${p.delivery.channel_label}` : `delivered ${p.delivery.kind} only`}
      </span>
      <time dateTime={received}>{p.ran_at_stamp.replace('_', ' ')} (fleet clock) · held {new Date(received).toUTCString().slice(17, 25)}</time>
    </>
  )
}

function DiscordExtras({ p }: { p: DiscordMessagePayload }) {
  return (
    <>
      {p.embeds.map((e, i) => (
        <div className={styles.embed} key={i}>
          {e.title && <strong>{e.title}</strong>}
          {e.description && <span>{e.description}</span>}
          {e.fields.map((f, j) => <span key={j}>{f.name}: {f.value}</span>)}
        </div>
      ))}
      {p.attachments.length > 0 && (
        <div className={styles.attachments}>
          {p.attachments.map((a, i) => <span key={i}>{a.filename}{a.size != null ? ` · ${Math.round(a.size / 1024)} KB` : ''}</span>)}
        </div>
      )}
    </>
  )
}
