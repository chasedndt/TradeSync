import type { QuarantineItem } from '../api/types'

/**
 * A human rendering of one quarantined item, by payload schema. The raw
 * JSON stays available behind a disclosure; the summary is what an operator
 * reads. Nothing here changes what the item is: untrusted material.
 */
export function summarise(item: QuarantineItem): { title: string; who: string; body: string; extra: string[] } {
  const p = item.payload as Record<string, unknown>
  const schema = String(p.schema_version ?? '')
  if (schema === 'tradingview_alert_v1') {
    const alert = (p.alert ?? {}) as Record<string, unknown>
    return {
      title: `${String(p.indicator ?? 'indicator')} · ${String(p.ticker ?? '')} ${p.interval ? `${p.interval}m` : ''}`.trim(),
      who: `TradingView alert${alert.exchange ? ` · ${String(alert.exchange)}` : ''}`,
      body: [p.action ? `action: ${String(p.action)}` : '', alert.note ? `note: ${String(alert.note)}` : '', alert.close ? `close: ${String(alert.close)}` : '']
        .filter(Boolean).join(' · ') || 'no action or note in the alert body',
      extra: alert.time ? [`alert time ${String(alert.time)}`] : [],
    }
  }
  if (schema === 'discord_message_v1') {
    const author = (p.author ?? {}) as Record<string, unknown>
    const embeds = (p.embeds ?? []) as { title?: string; description?: string }[]
    const embedText = embeds.map((e) => [e.title, e.description].filter(Boolean).join(': ')).filter(Boolean).join('\n')
    return {
      title: `${String(p.agent ?? 'channel')}`,
      who: `Discord · ${String(author.name ?? '')}${author.bot ? ' (bot)' : ''} · ${String(p.channel_kind ?? '')}`,
      body: [String(p.content ?? ''), embedText].filter(Boolean).join('\n') || '(no text)',
      extra: p.posted_at ? [`posted ${String(p.posted_at)}`] : [],
    }
  }
  if (schema === 'hermes_job_output_v1') {
    const delivery = (p.delivery ?? {}) as Record<string, unknown>
    return {
      title: String(p.agent ?? 'job'),
      who: `Hermes job ${String(p.job_id ?? '')}${p.schedule ? ` · ${String(p.schedule)}` : ''} · delivered ${delivery.kind === 'discord' ? `to ${String(delivery.channel_label)}` : String(delivery.kind ?? 'local')}`,
      body: String(p.content ?? ''),
      extra: p.ran_at_stamp ? [`fleet clock ${String(p.ran_at_stamp)}`] : [],
    }
  }
  if (item.source === 'agent_harness') {
    return {
      title: `harness · ${String(p.intent ?? 'answer')}`,
      who: `advisory harness${p.model ? ` · ${String(p.model)}` : ''}`,
      body: String(p.content ?? p.reason ?? ''),
      extra: p.prompt ? [`asked: ${String(p.prompt).slice(0, 200)}`] : [],
    }
  }
  return { title: item.source, who: schema || 'unknown schema', body: JSON.stringify(item.payload).slice(0, 600), extra: [] }
}

export function extractionLine(item: QuarantineItem): { text: string; tone: string } {
  const x = item.extraction
  if (!x || (!x.rule && !x.harness)) return { text: 'not yet read for claims', tone: 'tone-dim' }
  const parts: string[] = []
  if (x.rule) parts.push(x.rule.claims > 0 ? `rule: ${x.rule.claims} claim${x.rule.claims > 1 ? 's' : ''}` : `rule: ${x.rule.reason}`)
  if (x.harness) parts.push(x.harness.claims > 0 ? `harness: ${x.harness.claims} claim${x.harness.claims > 1 ? 's' : ''}` : `harness: ${x.harness.reason}`)
  const any = (x.rule?.claims ?? 0) + (x.harness?.claims ?? 0) > 0
  return { text: parts.join(' · '), tone: any ? 'tone-good' : 'tone-dim' }
}
